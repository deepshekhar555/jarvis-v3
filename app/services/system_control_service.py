"""Narrow Windows system-setting actions that run only after approval."""


def set_volume(value: int) -> str:
    if not 0 <= value <= 100:
        raise ValueError("Volume must be between 0 and 100.")
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    device = AudioUtilities.GetSpeakers()
    if device is None:
        raise RuntimeError("No audio output device is available.")
    activate = getattr(device, "Activate", None)
    if not callable(activate):
        raise RuntimeError("The audio output device does not support volume control.")
    interface = activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    # pycaw exposes this COM interface as object, while ctypes requires a pointer.
    volume = cast(interface, POINTER(IAudioEndpointVolume))  # type: ignore[arg-type]
    set_master_volume = getattr(volume, "SetMasterVolumeLevelScalar", None)
    if not callable(set_master_volume):
        raise RuntimeError("The audio device does not support master volume control.")
    set_master_volume(value / 100, None)
    return f"System volume set to {value}%."


def set_brightness(value: int) -> str:
    if not 0 <= value <= 100:
        raise ValueError("Brightness must be between 0 and 100.")
    import screen_brightness_control

    screen_brightness_control.set_brightness(value)
    return f"Screen brightness set to {value}%."
