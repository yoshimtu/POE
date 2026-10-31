from exile.map_icons import catalog,icon_key,original_image,icon_image
from exile.model import Mark


def test_all_bundled_icons_decode_and_exact_monster_art_is_selected():
    assert len(catalog())>=305
    assert all(not original_image(key).isNull()for key in catalog())
    assert icon_key({'native_icon':'Waypoint'},'rare')=='poe2:RareMonsterAlive'
    assert icon_key({},'unique')=='poe2:UniqueMonsterAlive'
    assert icon_key({},'normal')=='poe2:RareMonsterAlive'
    assert icon_key({},'magic')=='poe2:RareMonsterAlive'


def test_native_object_icons_win_then_specific_fallbacks_apply():
    assert icon_key({'native_icon':'AbyssChestActive'},'abyss')=='poe1:AbyssChestActive'
    assert icon_key({'native_icon':'does-not-exist','name':'Verisium Outcrop'},'settlers')=='poe1:OreTypeVerisium'
    assert icon_key({'name':'Eater of Worlds Altar'},'eldritch')=='poe1:TangleAltar'
    assert icon_key({'name':'Searing Exarch Altar'},'eldritch')=='poe1:CleansingFireAltar'
    assert icon_key({'name':'Cursed Treasure'},'allflame')=='poe1:DeepwaterCursedTreasure'
    assert icon_key({'name':'Brinerot Plunder'},'allflame')=='poe1:BrinerotStores'
    assert icon_key({},'expedition')=='poe1:ExpeditionDetonator'
    assert icon_key({},'not-a-category')==''


def test_icon_cache_preserves_aspect_and_invalid_key_is_safe():
    assert original_image('poe1:../../secret').isNull()
    image=icon_image('poe2:RareMonsterAlive',24,2)
    assert not image.isNull() and max(image.width(),image.height())==48
    assert icon_image('poe2:RareMonsterAlive',24,2)is image


def test_icon_draw_respects_alpha_clip_and_removes_when_mark_is_gone():
    from PySide6.QtGui import QImage,QPainter
    import numpy as np
    from exile.overlay import paint_marks,batch_dots
    image=QImage(80,80,QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
    mark=Mark('dot',40,40,size=8,value=.5,clip=(0,0,40,80),payload=dict(icon='poe2:RareMonsterAlive',icon_scale=100))
    assert list(batch_dots([mark,mark]))[0].kind=='icon_batch'
    painter=QPainter(image);paint_marks(painter,[mark]);painter.end()
    pixels=np.frombuffer(image.bits(),dtype=np.uint8).reshape(80,80,4)
    assert pixels[:,:40,3].max()in range(125,130)
    assert not pixels[:,40:,3].any()
    image.fill(0);painter=QPainter(image);paint_marks(painter,[]);painter.end()
    assert not np.frombuffer(image.bits(),dtype=np.uint8).any()

def test_blue_skull_changes_hue_without_changing_alpha_brightness_or_shape():
    import numpy as np
    from PySide6.QtGui import QImage
    from exile.map_icons import recolored_image
    images=[original_image('poe2:RareMonsterAlive'),recolored_image('poe2:RareMonsterAlive','#719cfa')]
    pixels=[]
    for image in images:
        rgba=image.convertToFormat(QImage.Format.Format_RGBA8888)
        pixels.append(np.frombuffer(rgba.constBits(),dtype=np.uint8).reshape(rgba.height(),rgba.width(),4).copy())
    before,after=pixels
    assert np.array_equal(before[:,:,3],after[:,:,3])
    assert np.array_equal(before[:,:,:3].max(axis=2),after[:,:,:3].max(axis=2))
    mask=before[:,:,3]>200
    assert after[:,:,2][mask].mean()>after[:,:,0][mask].mean()
    assert not np.array_equal(before,after)
    assert recolored_image('poe2:RareMonsterAlive','#719cfa')is images[1]

def test_magic_monster_icon_uses_blue_tint_and_smaller_category_size():
    from pathlib import Path
    from exile.plugins import PluginManager
    from exile.model import Snapshot
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    radar=next(p for p in manager.plugins if p.id=='radar');markers=[]
    for rarity in (0,1,2,3):
        s=Snapshot(source='preview',entities=[dict(kind='monster',rarity=rarity,grid=(10,10),life=10,max_life=10,alive=True,hostile=True)])
        markers.append(next(m for m in radar.tick(s,object())if m.kind=='dot'))
    normal,magic,rare,unique=markers
    assert normal.size<magic.size<rare.size<unique.size
    assert normal.payload['icon_tint']=='#dc6464'
    assert normal.payload['icon_minimum']==8
    assert max(normal.payload['icon_minimum'],normal.size*4)<max(magic.payload['icon_minimum'],magic.size*4)
    assert magic.payload['icon']=='poe2:RareMonsterAlive'
    assert magic.payload['icon_tint']=='#719cfa'
    assert not rare.payload['icon_tint'] and not unique.payload['icon_tint']
