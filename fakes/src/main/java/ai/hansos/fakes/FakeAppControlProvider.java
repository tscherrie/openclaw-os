package ai.hansos.fakes;

public final class FakeAppControlProvider {
    public String inspectNetworkSettings() {
        return "fake_settings.network: wifi=VirtWifi, mobile=connected, tailscale=pending";
    }
}
