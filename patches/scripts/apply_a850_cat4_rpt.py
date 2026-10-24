"""Adreno 850 (SM8975) category-4 repeat workaround.

On chip_id 0x44051431 repeating a category-4 / SFU instruction does not produce
the value the compiler expects, so the shaders DXVK generates for sRGB
conversion end up with the wrong channel values: R, G and B come out identical,
which renders menu UI, HUD and video playback as grayscale, while 3D geometry
that samples plain RGBA textures still looks correct. Reported as "the blue
channel is copied into the other two channels".

Keep the repeat merge disabled for this chip only, until the encoding or the
execution semantics behind the mismatch are understood.

Needs to be applied to both the android and the linux build: patching only the
linux runtime driver leaves the grayscale output in place.

Reported and validated on Adreno 850v2 hardware by @misakayuuki in
Droid-Deck/DroidDeck#980, reproduced and confirmed fixed on a second SM8975
device through Droid-Deck/Drivers#8.
"""
from mesa_edit import replace

IR3 = 'src/freedreno/ir3/ir3.c'

ANCHOR = (
    '   case 4:\n'
    '      return opc != OPC_RCP;\n'
)

PATCHED = (
    '   case 4:\n'
    '      /* Adreno 850 (SM8975, KGSL chip_id 0x44051431) miscomputes repeated\n'
    '       * category-4 instructions: sRGB conversion shaders come out with the\n'
    '       * wrong channel values, which shows up as grayscale 2D output.\n'
    '       */\n'
    '      if (compiler->dev_id &&\n'
    '          compiler->dev_id->chip_id == UINT64_C(0x44051431))\n'
    '         return false;\n'
    '      return opc != OPC_RCP;\n'
)

replace(IR3, ANCHOR, PATCHED, 'A850 category-4 repeat workaround')
