from exile.model import Mark, Plugin


class Hazards(Plugin):
    id, name, category = "hazards", "Hazard highlighting", "Awareness"
    description = "High-contrast rings around positively identified hazards, including volatile cores."
    requires = {"hazards"}
    defaults = {"labels": True, "minimum_radius": 24}
    fields = {"labels": ("Show hazard names", "bool"),
              "minimum_radius": ("Minimum ring radius", "int", 10, 100)}

    def tick(self, snapshot, ctx):
        return [Mark("ring", *h["screen"], h.get("name", "Hazard") if self.settings["labels"] else "",
                     "#ff8d59", max(self.settings["minimum_radius"], min(400, h.get("radius", 24))))
                for h in snapshot.hazards[:1000] if h.get("screen") and h.get("active", False)]


def create_plugin():
    return Hazards()
