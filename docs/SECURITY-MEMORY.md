# HansOS Security, Memory, and Autonomy

## Autonomy Defaults

Hans starts with autonomous default rules. The first alpha allows safe local
actions without repeated confirmation. External actions are represented through
fake providers until policy has enough real-device coverage.

## Local Memory

Memory is local and inspectable. The first implementation stores memory as
structured events owned by `HansManagerService`:

- user rules
- observed approvals and rejections
- daily-phone context
- action audit
- repairs and undo records

The first skeleton exposes memory as JSON through Binder. Later versions should
move it to an encrypted system database.

## Audit

Every action emits an audit event with:

- timestamp
- flow
- action
- result
- undo availability

Audit never leaves the device by default.

## Recovery

The product vision is ADB-only recovery. The first alpha keeps no visible
classic app drawer or rescue launcher. Debug recovery is done through:

```text
adb shell service call hans ...
adb shell am start ...
adb logcat -s HansManagerService HansRuntimeService HansCanvas
```
