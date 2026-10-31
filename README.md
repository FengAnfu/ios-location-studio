# iOS Location Studio

[中文](#中文) · [English](#english)

A local desktop controller for iOS 17+ location simulation. / 面向 iOS 17+ 的本机桌面定位模拟工具。

## 中文

### 功能

- USB 设备发现、持久连接和自动隧道，无需手动启动管理员隧道。
- 瞬移、键盘摇杆、路线播放、GPX 导入、速度调节。
- 可选起步加速、转弯减速和定位抖动，用于应用开发与定位测试。
- 本机认证接口、Host / Origin 校验、输入与请求大小限制。
- 无手机演示模式，以及停止后恢复真实定位指令。

通过 Apple 开发者服务模拟设备报告的位置。应用是否采用此来源取决于其实现；这不会改变设备 IP、基站位置或所有应用的定位来源。用于你拥有或获授权的设备与应用测试。

### 安装与启动

需要 macOS、Python 3.12 和 iOS 17+ 设备。当前依赖清单在 macOS / Python 3.12 环境解析。其他平台未经验证。

```sh
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
python run.py
```

1. 用 USB 连接手机，解锁后信任此电脑。
2. 在手机“设置 → 隐私与安全性”中开启开发者模式，按提示重启并确认开启。
3. 选择设备并连接。首次连接可能下载并准备 Developer Disk Image，请保持手机解锁。
4. 在地图选择位置，或填写 WGS84 纬度、经度，点击 **Teleport here**。
5. 使用结束时点击“停止并恢复真实定位”，并在手机地图中确认。

若系统不显示开发者模式入口，可先运行 `python -m pymobiledevice3 amfi reveal-developer-mode`，然后重新打开手机设置。这只显示入口，开启与重启仍需在手机上确认。

服务仅监听 `127.0.0.1`。无法打开桌面窗口时，在浏览器打开启动器输出的完整本机地址；地址包含访问凭据，请勿分享。端口被占用时使用 `FAKEGPS_PORT=0 python run.py` 自动选择可用端口。

### 演示与测试

```sh
FAKEGPS_DEMO=1 python run.py
python -m unittest discover -s tests -v
node --check frontend/app.js
```

演示模式只更新内存中的假设备。常速路线逐点生成；路线总长限制为 1,000 公里，最多 10,000 个航点，速度范围为 0.5–30 m/s。

### 已验证与限制

- 12 项自动测试通过，覆盖认证、来源校验、参数边界、GPX、WebSocket、定位恢复错误和路线惰性生成。
- 本机服务的演示路线连续推送、停止、摇杆和正常退出已验证。
- 已在 iOS 27.0.1 设备上验证连接与瞬移，并通过设备上的地图确认位置变化。
- 尚未逐一验证所有系统版本、应用或设备。恢复指令成功不代表所有应用已更新缓存。
- 在线地图使用 OpenStreetMap，瓦片请求会暴露查看区域；Leaflet CDN 资源带有完整性校验。浏览器真实定位只在主动点击时请求。

### 项目结构

```text
run.py                 桌面启动器
backend/app.py         设备会话和 REST / WebSocket 接口
backend/security.py    本机认证与请求限制
backend/routing.py     路线计算和 GPX 解析
backend/devices/       iOS 与演示驱动
frontend/              静态地图界面
tests/                 无手机自动测试
```

### 许可证

本仓库源码采用 MIT 协议，保留原项目版权声明。第三方依赖遵循各自许可证，见 [第三方说明](THIRD_PARTY_NOTICES.md)。

## English

### Features

- USB discovery, persistent device sessions and an automatic tunnel without a separate administrator daemon.
- Teleport, keyboard joystick, route playback, GPX import and adjustable speed.
- Optional acceleration, corner braking and location noise for application development and location testing.
- Authenticated local APIs, Host / Origin validation and bounded input sizes.
- A hardware-free demo and a command to stop simulation and restore real location.

The tool uses Apple's developer services to simulate the device's reported location. Whether an application uses that source depends on its implementation. It does not change the device IP address, cellular location or every application's location source. Use it with devices and applications you own or are authorized to test.

### Setup and launch

Requires macOS, Python 3.12 and an iOS 17+ device. The dependency constraints were resolved on macOS / Python 3.12. Other platforms have not been validated.

```sh
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
python run.py
```

1. Connect the unlocked device over USB and trust the computer.
2. Enable Developer Mode under Settings → Privacy & Security. Restart and confirm on the device.
3. Select the device and connect. The first connection may download and prepare a Developer Disk Image; keep the device unlocked.
4. Choose a map location or enter WGS84 latitude and longitude, then select **Teleport here**.
5. Select the restore button when finished and verify the real location in the device's map application.

If the Developer Mode entry is hidden, run `python -m pymobiledevice3 amfi reveal-developer-mode` and reopen Settings. This only reveals the entry; enabling it and restarting still require confirmation on the device.

The service binds only to `127.0.0.1`. If the desktop window is unavailable, open the full local URL printed by the launcher. The URL contains an access credential and should not be shared. Use `FAKEGPS_PORT=0 python run.py` to choose an available port automatically.

### Demo and tests

```sh
FAKEGPS_DEMO=1 python run.py
python -m unittest discover -s tests -v
node --check frontend/app.js
```

Demo mode updates only an in-memory device. Constant-speed routes are generated lazily. Routes are limited to 1,000 km and 10,000 waypoints, with a speed range of 0.5–30 m/s.

### Validation and limitations

- Twelve automated tests cover authentication, origin checks, input bounds, GPX, WebSocket access, restore errors and lazy route generation.
- Demo route streaming, stop, joystick and graceful shutdown were checked against a running local server.
- Device connection and teleport were validated on iOS 27.0.1, with the location change confirmed in a map application on the device.
- Every OS version, application and device has not been tested. A successful restore command does not prove all applications have refreshed cached locations.
- Map tiles are requested from OpenStreetMap and reveal the viewed region. Leaflet CDN assets include integrity hashes. Browser geolocation is requested only by an explicit user action.

### Layout

```text
run.py                 Desktop launcher
backend/app.py         Device session and REST / WebSocket endpoints
backend/security.py    Local authentication and request bounds
backend/routing.py     Route calculations and GPX parsing
backend/devices/       iOS and demo drivers
frontend/              Static map interface
tests/                 Hardware-free tests
```

### License

Repository source code is MIT licensed, retaining the original copyright notice. Third-party dependencies retain their respective licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).
