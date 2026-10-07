# App v0.6 native QSFP selection

In the Firewall mapping section, selecting PA-5410 ethernet1/41–44 exposes a Native Link Speed selector with 40G and 100G. No speed is selected by default. The choice is sent as `target_settings.link_speed` with the manual mapping and saved with the project's local reference. The UI shows compatibility findings and uses the existing review acknowledgement before candidate generation.

Ports 1–24 retain their normal flow. Breakout children 25–40 remain blocked and offer no native speed control. The interface layout and Switch workspace are unchanged. The evidence panel identifies the documentation sources; physical PA-5410 validation has not been performed.
