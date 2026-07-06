import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const processorPath = path.resolve(__dirname, '../stereo_perception_multi2_offline_test/src/offline_processor.cpp')
const source = fs.readFileSync(processorPath, 'utf8')

const filterMatch = source.match(
  /static void filterLabelDect[\s\S]*?\n\}/,
)
assert.ok(filterMatch, 'filterLabelDect implementation should be present')
const filterSource = filterMatch[0]

assert.doesNotMatch(
  filterSource,
  /force_bottom_region|force_region|shift_high/,
  'Model 6 label filtering should not force a fixed bottom region to label 2',
)

assert.match(
  filterSource,
  /cv::compare\s*\(\s*lab_dst\s*,\s*0[\s\S]*?lab_dst\.setTo\s*\(\s*2\s*,\s*mask_zero\s*\)/,
  'Model 6 label filtering should match the reference path by normalizing label 0 to label 2',
)

const model6Match = source.match(
  /OfflineProcessor::ProcessResult OfflineProcessor::processModel6[\s\S]*?OfflineProcessor::ProcessResult OfflineProcessor::processModel7/,
)
assert.ok(model6Match, 'processModel6 implementation should be present')
const model6Source = model6Match[0]

assert.doesNotMatch(
  model6Source,
  /force_bottom|filterLabelDect\s*\([^;]*force_bottom/,
  'Model 6 should not derive any hardware-specific label forcing flag',
)

assert.match(
  model6Source,
  /if\s*\(\s*hardware_mode_\.isK100Hardware\(\)\s*\)[\s\S]*cv::Rect\s+crop_region\s*\(\s*0\s*,\s*0\s*,\s*640\s*,\s*432\s*\)[\s\S]*cv::resize\s*\(\s*cropped_img\s*,\s*resized_img\s*,\s*cv::Size\s*\(\s*640\s*,\s*384\s*\)/,
  'Model 6 K100 should crop 432 and resize to 384 before fusion',
)

assert.match(
  model6Source,
  /else\s*\{[\s\S]*cv::Rect\s+crop_region\s*\(\s*0\s*,\s*0\s*,\s*640\s*,\s*384\s*\)[\s\S]*resized_img\s*=\s*cropped_img\.clone\(\)/,
  'Model 6 bestmow should crop 384 and use it directly',
)

assert.doesNotMatch(
  model6Source,
  /result\.segmentation\s*=\s*lab_dst/,
  'Model 6 should keep the processing segmentation at 384 and resize only for K100 visualization',
)

assert.match(
  model6Source,
  /stereo_process_pci_depth_rgb_seg_det_fusion\s*\([\s\S]*fusion_img,\s*\/\/ K100: 640x432/,
  'Model 6 K100 fusion should match the reference 640x432 point-cloud fusion path',
)

assert.match(
  model6Source,
  /stereo_process_pci_depth_rgb_seg_det_fusion_bestmow\s*\([\s\S]*fusion_img,\s*\/\/ bestmow: 640x384/,
  'Model 6 bestmow fusion should match the reference 640x384 point-cloud fusion path',
)

assert.match(
  model6Source,
  /if\s*\(\s*hardware_mode_\.isK100Hardware\(\)\s*\)[\s\S]*result\.depth\s*=\s*depth_480\s*\(\s*cv::Rect\s*\(\s*0,\s*0,\s*640,\s*432\s*\)\s*\)\.clone\(\)[\s\S]*else\s*\{[\s\S]*result\.depth\s*=\s*depth_480\s*\(\s*cv::Rect\s*\(\s*0,\s*0,\s*640,\s*384\s*\)\s*\)\.clone\(\)/,
  'Model 6 depth should match the reference K100 432 / bestmow 384 fusion sizes',
)

const saveMatch = source.match(/void OfflineProcessor::saveResults[\s\S]*?\/\/ 保存点云/)
assert.ok(saveMatch, 'saveResults implementation should be present')
const saveSource = saveMatch[0]

assert.match(
  saveSource,
  /config_\.infer_mode\s*==\s*6[\s\S]*hardware_mode_\.isK100Hardware\(\)[\s\S]*cv::resize\s*\(\s*result\.segmentation\s*,\s*vis_segmentation\s*,\s*cv::Size\s*\(\s*640\s*,\s*432\s*\)/,
  'Model 6 K100 visualization should resize segmentation back to 432',
)

console.log('model6-hardware-size-contract test passed')
