import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), 'utf8')
}

function assertFile(relativePath, message) {
  assert.ok(fs.existsSync(path.join(root, relativePath)), message)
}

assertFile(
  'stereo_perception_multi2_offline_test/include/semantic_depth_utils.hpp',
  'offline pipeline should include the reference semantic depth helpers',
)
assertFile(
  'stereo_perception_multi2_offline_test/src/semantic_depth_utils.cpp',
  'offline pipeline should implement the reference semantic depth helpers',
)
assertFile(
  'stereo_perception_multi2_offline_test/src/single_segmentation_compare.cpp',
  'offline pipeline should include the reference single-image segmentation comparison executable',
)

const processor = read('stereo_perception_multi2_offline_test/src/offline_processor.cpp')

assert.match(
  processor,
  /#include "semantic_depth_utils\.hpp"/,
  'offline processor should use the reference semantic depth utilities',
)
assert.match(
  processor,
  /cv::compare\s*\(\s*lab_dst\s*,\s*0\s*,\s*mask_zero\s*,\s*cv::CMP_EQ\s*\)[\s\S]*lab_dst\.setTo\s*\(\s*2\s*,\s*mask_zero\s*\)/,
  'reference label filtering normalizes model label 0 to label 2',
)
assert.match(
  processor,
  /depthInpaintingForObstacles\s*\(/,
  'model processing should use the reference semantic obstacle depth inpainting path',
)
const depthInpainting = read('stereo_perception_multi2_offline_test/src/offline_processor_depth_inpainting.cpp')
assert.match(
  depthInpainting,
  /return\s+inpaintSemanticObstacleDepth\s*\(\s*depth\s*,\s*protected_label\s*\)/,
  'semantic obstacle depth inpainting should delegate to the reference semantic-depth helper',
)

const singleCompare = read('stereo_perception_multi2_offline_test/src/single_segmentation_compare.cpp')
assert.match(
  singleCompare,
  /cv::resize\s*\(\s*original_img\s*,\s*resized\s*,\s*cv::Size\s*\(\s*kModelWidth\s*,\s*kModelHeight\s*\)/,
  'single-image compare should resize input images to the model input size before inference',
)
assert.match(
  singleCompare,
  /normalizeSubLabel[\s\S]*normalized\.setTo\s*\(\s*2\s*,\s*zero_mask\s*\)/,
  'single-image compare should apply the same label-0 normalization as the reference',
)
assert.match(
  singleCompare,
  /cv::hconcat\s*\(\s*std::vector<cv::Mat>\s*\{\s*original_img\s*,\s*pure_seg\s*,\s*overlay\s*\}/,
  'single-image compare should write original, pure segmentation, and overlay panels',
)

const cmake = read('stereo_perception_multi2_offline_test/CMakeLists.txt')
for (const source of [
  'src/offline_processor_depth_inpainting.cpp',
  'src/offline_processor_red_brick.cpp',
  'src/cdt_perception.cpp',
  'src/label_postprocess.cpp',
  'src/semantic_depth_utils.cpp',
]) {
  assert.match(cmake, new RegExp(source.replaceAll('.', '\\.')), `CMake should compile ${source}`)
}
assert.match(
  cmake,
  /add_executable\s*\(\s*single_segmentation_compare/,
  'CMake should build the reference single-image comparison executable',
)
assert.doesNotMatch(
  cmake,
  /\/home\/youfeng\/CLionProjects\/05-offline_debug_fusion\/deps_gcc11\.3/,
  'local CMake should not copy the reference machine-specific DNN absolute path',
)

console.log('stereo-reference-alignment test passed')
