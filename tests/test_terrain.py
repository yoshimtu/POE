
def test_null_tile_source_is_empty_height_payload_without_null_read():
    import struct
    from exile.terrain import decode_height_tiles
    tile=bytearray(56);struct.pack_into('<h',tile,48,12)
    def read_samples(pointer):raise AssertionError('Null source must not be read')
    result=decode_height_tiles(bytes(tile),1,1,read_samples)
    assert result.shape==(23,23) and (result==12).all()
