import pytest

from oci.data import synthetic as S


@pytest.fixture(scope="session")
def scenarios():
    return {name: S.load(name) for name in S.SCENARIOS}


@pytest.fixture(scope="session")
def screened(scenarios):
    from oci.physics.screen import screen
    return {name: screen(sc.objects, sc.window_start, sc.window_end) for name, sc in scenarios.items()}


def objects_of(sc):
    return {o.norad_id: o for o in sc.objects}
