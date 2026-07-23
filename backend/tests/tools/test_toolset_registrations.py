from app.tools.registrations import default_toolset_registrations


def test_default_toolset_registrations_include_only_weather() -> None:
    registrations = default_toolset_registrations({})

    assert tuple(registration.name for registration in registrations) == ("weather",)
