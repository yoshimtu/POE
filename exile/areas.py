"""Safe hub detection shared by the reader and visual plugins."""
SAFE_NAMES=frozenset(("lioneye's watch",'forest encampment','sarn encampment','highgate',
    "overseer's tower",'bridge encampment','oriath','karui shores','kingsmarch','rogue harbour',
    'menagerie',"aspirants' plaza","aspirant's plaza"))


def town_or_hideout(area_id,area_name=''):
    identity=area_id.casefold()
    name=area_name.casefold().replace('’',"'").strip()
    if name.startswith('the '):name=name[4:]
    if identity.startswith('hideout'):return True
    if name in SAFE_NAMES:return True
    return 'town'in identity and not identity.startswith(('mapworlds','map','atlas'))


def safe_area(snapshot):
    return snapshot.source=='live'and(bool(snapshot.town)or town_or_hideout(snapshot.area_id,snapshot.area))
