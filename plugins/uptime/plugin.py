from exile.model import Mark, Plugin


class Uptime(Plugin):
    id, name, category = "uptime", "Buff & defensive uptime", "Awareness"
    description = "Track reported buff durations and flag configured missing defenses."
    requires = {"buffs"}
    defaults = {"required": "", "flasks": True,"exclusions":"","overlay_size":[],"overlay_position":[],"overlay_locked":False}
    fields = {"required": ("Required buff ids, one per line", "text"),
              "flasks": ("Include flask effects", "bool"),"exclusions":("Excluded buffs (one per line; remove a line to restore)","text"),"overlay_locked":("Lock overlay position and size (click through)","bool")}

    def tick(self, snapshot, ctx):
        buffs = [b for b in snapshot.buffs if self.settings["flasks"] or not b.get("flask")]
        required = {x.strip().casefold() for x in self.settings["required"].splitlines() if x.strip()}
        active = {b.get("id", "").casefold() for b in buffs}
        rows = [("Missing: " + name, "#e88480") for name in sorted(required - active)]
        rows += [(f"{b.get('name', b.get('id', 'Buff'))}  " +
                  (f"{b['remaining']:.1f}s" if b.get("remaining") is not None else "active"), "#91c7b1")
                 for b in buffs]
        excluded={n.strip().casefold()for n in self.settings['exclusions'].splitlines()if n.strip()}
        keys=[name for name in sorted(required-active)]+[b.get('name',b.get('id','Buff'))for b in buffs]
        visible=[dict(label=t,color=c,evidence='',buff_key=key)for (t,c),key in zip(rows,keys)if key.casefold()not in excluded]
        return [Mark('uptime_panel',30,350,payload=dict(rows=visible[:16],settings=dict(self.settings)))]if visible else []


def create_plugin():
    return Uptime()
