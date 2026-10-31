# Direct Foulborn detection

Live read-only samples in Monastery of the Keepers:
- Warped Timepiece: identified=true; MutatedUniqueAmulet20CurseEffectTemporalChains.
- Rigwald's Quills: identified=true; MutatedUniqueQuiver10ChanceToAggravateBleed.
- The Formless Flame, Agnerod West and Immutable Force: identified=true; complete explicit modifier vectors with ordinary identifiers, no MutatedUnique prefix.

Verified current offsets, editable in steam-25113903.read-only.json: identified byte 0xb0; explicit modifier vector 0xd8; record stride 0x38; definition pointer +0x28; definition identifier pointer +0. Reader validates component ownership before/after traversal, bounded vector size, identifier syntax and unchanged vector header. Missing/empty/unreadable records remain unknown, not false. This detects the MutatedUnique modifier rather than assuming an unverified influence bit.

Foulborn=true selects Foulborn-prefixed provider names even though the game's internal unique name lacks the prefix. False excludes Foulborn candidates; unknown keeps the requested three-area fallback. Variant evidence participates in quote identity to prevent ordinary and mutated items sharing cached quotes. Multiple provider modifier variants remain a reference range until the exact variant mapping is established. Named identified Foulborn items remain priced anywhere.

197 tests passed, exit 0, including positive/negative/empty modifier evidence and distinct quote keys/provider names. No gameplay inputs sent. User no longer needs to keep the samples on the ground.
Release 20261029-164208: packaged checks passed and new app launched. Cached provider data contains matching Foulborn Warped Timepiece (Temporal Chains) and Foulborn Rigwald's Quills (Aggravate Bleed) entries.
