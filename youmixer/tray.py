"""Icon next to the Windows clock: open the page, switch profile or turn YouMixer off."""
import threading

from .i18n import t

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:  # Not installed yet: the app works the same, just without the icon
    pystray = None

LOGO = (195, 154, 85, 255)  # sepia of the logo plate
INK = (22, 22, 22, 255)


def available():
    return pystray is not None


def make_image():
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=12, fill=LOGO)
    draw.polygon([(24, 16), (24, 48), (50, 32)], fill=INK)
    return image


class Tray:
    """`actions` holds what the menu does, so the icon doesn't depend on the rest of the app:
    open(mode or None), on_quit(), profiles() → (active id, [profiles]), switch_profile(id), window_available()."""

    def __init__(self, actions):
        self.actions = actions
        self.icon = None
        self.lock = threading.Lock()

    @property
    def visible(self):
        return self.icon is not None

    def _profile_item(self, profile_id, name):
        # pystray only accepts callbacks with 0 to 2 arguments, so each profile gets its own
        return pystray.MenuItem(
            name,
            lambda icon, item: self.actions["switch_profile"](profile_id),
            checked=lambda item: self.actions["profiles"]()[0] == profile_id,
            radio=True,
        )

    def _profile_items(self):
        _, profiles = self.actions["profiles"]()
        return [self._profile_item(profile["id"], profile["name"]) for profile in profiles]

    def _menu(self):
        # Texts are callables so the menu always shows up in the current language
        return pystray.Menu(
            pystray.MenuItem(lambda item: t("tray.open"), lambda: self.actions["open"](None), default=True),
            pystray.MenuItem(lambda item: t("tray.open_browser"), lambda: self.actions["open"]("browser")),
            pystray.MenuItem(lambda item: t("tray.open_window"), lambda: self.actions["open"]("window"),
                             enabled=lambda item: self.actions["window_available"]()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: t("tray.profile"), pystray.Menu(lambda: self._profile_items())),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: t("tray.quit"), self.quit),
        )

    def show(self):
        with self.lock:
            if self.icon or not pystray:
                return
            self.icon = pystray.Icon("YouMixer", make_image(), "YouMixer", self._menu())
            threading.Thread(target=self.icon.run, daemon=True).start()

    def hide(self):
        with self.lock:
            if self.icon:
                self.icon.stop()
                self.icon = None

    def refresh(self):
        """Rebuilds the menu after the language or the profiles change."""
        with self.lock:
            if self.icon:
                try:
                    self.icon.update_menu()
                except Exception:  # the icon may still be starting; the menu is built then anyway
                    pass

    def quit(self, *_):
        self.hide()
        self.actions["on_quit"]()
