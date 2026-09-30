from mesa_edit import replace

replace(
    'src/freedreno/common/freedreno_devices.py',
    '        GPUId(chip_id=0xffff43050c01, name="Adreno X1-85"),\n'
    '    ], A6xxGPUInfo(\n'
    '        CHIP.A7XX,\n'
    '        [a7xx_base, a7xx_gen2],\n',
    '        GPUId(chip_id=0xffff43050c01, name="Adreno X1-85"),\n'
    '    ], A6xxGPUInfo(\n'
    '        CHIP.A7XX,\n'
    '        [a7xx_base, a7xx_gen2, GPUProps(enable_tp_ubwc_flag_hint = True)],\n',
    'enable_tp_ubwc_flag_hint for FD740 / X1-85',
)
