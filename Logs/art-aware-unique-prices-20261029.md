# Art-aware unidentified unique pricing

The reader now optionally decodes RenderItem's resource pointer at profile offset 0x28, validates component ownership and an Art/2DItems/*.dds path. Invalid/unavailable art is ignored without losing the item. This offset was verified against the live Spidersilk Robe (SoulMantle.dds), Immutable Force (RedJewel2.dds) and unique synthesis maps. Reference 0x20 was not valid on this build.

Pricing decodes poe.ninja generated icon source assets and excludes confirmed art mismatches for unnamed uniques. It normalizes extension/case, retains missing provider art, and includes actual item art in quote/cache identities. This applies across ground, backpack and stash through their shared reader and valuation path. No hardcoded robe name exclusions.

Live robe candidates reduced from five to Soul Mantle and Foulborn Soul Mantle. Foulborn/mutated and replica flags were not independently verified; matching art variants remain candidates. No specific unique identity is claimed from art shared by multiple variants.

194 tests passed, including source-icon decoding, conflicting art rejection, missing-art fallback, preserved mutation uncertainty and distinct art quote keys. Live read-only validation confirmed the robe's source art and the two remaining cached feed entries.
`nRelease: releases/20261029-160725/ObsidianExile. Packaged checks passed with seven modules and no errors; updated app launched.
