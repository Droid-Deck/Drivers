import ast
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / 'patches' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from mesa_edit import has_gpu_chip_id

CHIP_ID = 0x44050100
DEVICE_PATH = 'src/freedreno/common/freedreno_devices.py'
A830 = '        GPUId(chip_id=0x44050001, name="Adreno (TM) 830"), # KGSL\n'

# Keep the other A8xx edits already applied so these tests isolate the A831 addition.
DEVICES = '''
add_gpus([
       GPUId(chip_id=0x44010000, name="Adreno (TM) 810"),
       GPUId(chip_id=0xffff44010000, name="Adreno (TM) 810"),
    ], A6xxGPUInfo(
        CHIP.A8XX,
        [a7xx_base, a7xx_gen3, a8xx_base, a8xx_gen1, a8xx_vpc_cache_sm, GPUProps(
            # This is possibly also needed for a830 (and all of a8xx),
            # move to a8xx_base if confirmed needed for a830.
            has_fs_tex_prefetch = False,
            disable_gmem = True,
        )]))
add_gpus([
        GPUId(chip_id=0x44030A00, name="Adreno (TM) 829"),
        GPUId(chip_id=0xffff44030A00, name="Adreno (TM) 829"),
        GPUId(chip_id=0x44030a20, name="Adreno (TM) 829"), # KGSL
    ], A6xxGPUInfo(
        CHIP.A8XX,
        [a7xx_base, a7xx_gen3, a8xx_base, a8xx_gen2, a8xx_vpc_cache_med,
         GPUProps(
            shading_rate_matches_vk = True,  # TODO confirm this
            disable_gmem = True,
        )]))
add_gpus([
        GPUId(chip_id=0x44050001, name="Adreno (TM) 830"), # KGSL
    ], a830_info)
add_gpus([
        GPUId(chip_id=0x44030000, name="Adreno (TM) 825"),
        GPUId(chip_id=0x44041430, name="Adreno (TM) 845"),
        GPUId(chip_id=0x44051431, name="Adreno (TM) 850"),
    ], other_info)
'''


class ChipIdTest(unittest.TestCase):
    def matches(self, source):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / 'devices.py'
            path.write_text(source)
            return has_gpu_chip_id(path, CHIP_ID)

    def test_matches_numeric_chip_id_independently_of_formatting(self):
        for number in ('0x44050100', '0X44050100', '0x4405_0100', str(CHIP_ID)):
            with self.subTest(number=number):
                self.assertTrue(self.matches(
                    f'GPUId(\n    name="renamed upstream",\n    chip_id = {number},\n)\n'))

    def test_ignores_mentions_outside_the_chip_id_argument(self):
        for source in (
            '# GPUId(chip_id=0x44050100)\n',
            'note = "GPUId(chip_id=0x44050100)"\n',
            'chip_id = 0x44050100\n',
            'GPUId(gpu_id=0x44050100)\n',
            'GPUProps(chip_id=0x44050100)\n',
            'GPUId(chip_id="0x44050100")\n',
            f'GPUId(chip_id={CHIP_ID}.0)\n',
            'GPUId(chip_id=0xffff44050100)\n',
            'GPUId(chip_id=0x440501001)\n',
        ):
            with self.subTest(source=source):
                self.assertFalse(self.matches(source))

    def test_invalid_python_fails_instead_of_assuming_the_device_is_absent(self):
        with self.assertRaises(SyntaxError):
            self.matches('GPUId(chip_id=')


class A831PatchTest(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.work = Path(work.name)
        self.devices = self.work / DEVICE_PATH
        self.devices.parent.mkdir(parents=True)

    def apply(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'apply_a8xx_gpus.py')],
                                cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.devices.read_text()

    def test_inserts_with_a830_despite_a_comment_and_is_idempotent(self):
        self.devices.write_text('# GPUId(chip_id=0x44050100) is not a device entry.\n' + DEVICES)
        patched = self.apply()
        groups = [call for call in ast.walk(ast.parse(patched))
                  if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                  and call.func.id == 'add_gpus' and isinstance(call.args[1], ast.Name)
                  and call.args[1].id == 'a830_info']
        self.assertEqual(len(groups), 1)
        ids = [kw.value.value for gpu in groups[0].args[0].elts
               for kw in gpu.keywords if kw.arg == 'chip_id']
        self.assertEqual(ids, [0x44050001, CHIP_ID])
        self.assertEqual(self.apply(), patched)

    def test_existing_upstream_entry_is_untouched_even_without_a830_anchor(self):
        source = DEVICES.replace(A830, '') + (
            'add_gpus([GPUId(name="Adreno (TM) 831",\n'
            '                chip_id = 0X4405_0100)], upstream_a831_info)\n')
        self.devices.write_text(source)
        self.assertEqual(self.apply(), source)

    def test_missing_a830_anchor_fails_when_a831_is_absent(self):
        self.devices.write_text(DEVICES.replace(A830, ''))
        result = subprocess.run([sys.executable, str(SCRIPTS / 'apply_a8xx_gpus.py')],
                                cwd=self.work, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('anchor missing for A831', result.stderr)


if __name__ == '__main__':
    unittest.main()
