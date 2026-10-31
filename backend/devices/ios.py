"""iOS 17+ device location simulation with a persistent no-root RSD tunnel.

All tunnel, DDI and DVT resources live on one dedicated asyncio thread. The
synchronous interface lets the control plane use asyncio.to_thread safely.
"""
from __future__ import annotations

import asyncio
import logging
import math
import threading
from contextlib import AsyncExitStack
from typing import Optional

from . import DeviceInfo, LocationDriver

log = logging.getLogger("fakegps.ios")


class IOSDriverError(RuntimeError):
    pass


def _major(version: str) -> int:
    try:
        return int(version.split(".", 1)[0])
    except (ValueError, AttributeError):
        return 0


async def _alist_devices() -> list[DeviceInfo]:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.usbmux import list_devices as usbmux_list

    found: list[DeviceInfo] = []
    seen: set[str] = set()
    for dev in await usbmux_list():
        if dev.serial in seen:
            continue
        seen.add(dev.serial)
        try:
            async with await create_using_usbmux(serial=dev.serial) as ld:
                if _major(ld.product_version) < 17:
                    continue
                name = await ld.get_value(key="DeviceName")
                found.append(DeviceInfo(udid=dev.serial, name=name or "iPhone",
                                        platform="ios", os_version=ld.product_version))
        except Exception as exc:
            log.warning("无法读取设备信息: %s", exc)
    return found


def list_devices() -> list[DeviceInfo]:
    try:
        return asyncio.run(_alist_devices())
    except ImportError as exc:
        raise IOSDriverError("请先安装 backend/requirements.txt 中的依赖") from exc


class IOSLocationDriver(LocationDriver):
    CALL_TIMEOUT = 300.0  # first DDI preparation may require a download

    def __init__(self, info: DeviceInfo):
        self.info = info
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._resources: Optional[AsyncExitStack] = None
        self._rsd = None
        self._sim = None
        self._operation_lock = threading.RLock()

    def _start_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop

        def run():
            asyncio.set_event_loop(loop)
            try:
                loop.run_forever()
            finally:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        self._thread = threading.Thread(target=run, name="ios-location", daemon=True)
        self._thread.start()

    def _call(self, coro, timeout: Optional[float] = None):
        if self._loop is None:
            coro.close()
            raise IOSDriverError("定位服务尚未启动")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout or self.CALL_TIMEOUT)
        except TimeoutError:
            future.cancel()
            raise IOSDriverError("设备响应超时，请解锁手机并检查 USB 连接后重试") from None

    def connect(self) -> "IOSLocationDriver":
        if _major(self.info.os_version) < 17:
            raise IOSDriverError("仅支持 iOS 17 及以上版本")
        self._start_loop()
        try:
            self._call(self._aconnect_modern())
        except Exception as exc:
            self.close()
            if isinstance(exc, IOSDriverError):
                raise
            raise IOSDriverError(f"无法连接设备定位服务：{type(exc).__name__}: {exc}") from exc
        return self

    async def _aconnect_modern(self) -> None:
        from pymobiledevice3.exceptions import AlreadyMountedError
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel
        from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
        from pymobiledevice3.services.mobile_image_mounter import auto_mount

        async with await create_using_usbmux(serial=self.info.udid) as ld:
            if not await ld.get_developer_mode_status():
                raise IOSDriverError("请在 iPhone 设置 → 隐私与安全性中开启开发者模式，重启并解锁确认")
        self._resources = AsyncExitStack()
        self._rsd = await self._resources.enter_async_context(PreferredRsdTunnel(serial=self.info.udid))
        try:
            await auto_mount(self._rsd)
        except AlreadyMountedError:
            pass
        dvt = await self._resources.enter_async_context(DvtProvider(self._rsd))
        self._sim = await self._resources.enter_async_context(LocationSimulation(dvt))
        log.info("iOS %s 定位服务连接成功（免管理员密码）", self.info.os_version)

    def set_location(self, lat: float, lon: float) -> None:
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise IOSDriverError("经纬度超出有效范围")
        with self._operation_lock:
            if self._sim is None:
                raise IOSDriverError("设备尚未连接")
            self._call(self._sim.set(lat, lon), timeout=30)

    def clear(self) -> None:
        with self._operation_lock:
            if self._sim is None:
                raise IOSDriverError("设备尚未连接，无法确认恢复定位")
            self._call(self._sim.clear(), timeout=30)

    async def _teardown(self) -> None:
        try:
            if self._resources is not None:
                await self._resources.aclose()
        finally:
            self._resources = self._rsd = self._sim = None

    def close(self) -> None:
        with self._operation_lock:
            if self._loop is None:
                return
            if self._sim is not None:
                try:
                    self.clear()
                except Exception as exc:
                    log.warning("退出时未能确认恢复定位: %s", exc)
            try:
                self._call(self._teardown(), timeout=30)
            except Exception as exc:
                log.warning("连接清理失败: %s", exc)
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=10)
            self._loop = self._thread = None


def open_driver(udid: str) -> IOSLocationDriver:
    for info in list_devices():
        if info.udid == udid:
            return IOSLocationDriver(info).connect()
    raise IOSDriverError("未找到 iOS 17+ 设备，请连接并解锁手机，在手机上信任此电脑")
