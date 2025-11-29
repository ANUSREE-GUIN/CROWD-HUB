<?php
header('Content-Type: application/json');

// Validate Request Method
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'message' => 'Invalid request method']);
    exit;
}

// Check uploaded media file
if (!isset($_FILES['mediafile'])) {
    echo json_encode(['success' => false, 'message' => 'No media file uploaded']);
    exit;
}

$uploadsDir = __DIR__ . DIRECTORY_SEPARATOR . 'uploads';
$outputsDir = __DIR__ . DIRECTORY_SEPARATOR . 'outputs';

if (!is_dir($uploadsDir)) mkdir($uploadsDir, 0777, true);
if (!is_dir($outputsDir)) mkdir($outputsDir, 0777, true);

$file = $_FILES['mediafile'];

if ($file['error'] !== UPLOAD_ERR_OK) {
    echo json_encode(['success' => false, 'message' => 'Upload error: ' . $file['error']]);
    exit;
}

$baseName = basename($file['name']);
$timestamp = time();
$targetPath = $uploadsDir . DIRECTORY_SEPARATOR . $timestamp . '_' . $baseName;

if (!move_uploaded_file($file['tmp_name'], $targetPath)) {
    echo json_encode(['success' => false, 'message' => 'Failed to move file']);
    exit;
}

////////////////////////////////////////////////////
// ✔ FIX: ACCEPT ZONES AS TEXT OR FILE
////////////////////////////////////////////////////
$zonesArg = '';
$zonesJson = null;

// If zones received as JSON text field
if (isset($_POST['zones']) && trim($_POST['zones']) !== '') {
    $zonesJson = $_POST['zones'];
}

// If zones received as JSON file
if (!$zonesJson && isset($_FILES['zones']) && $_FILES['zones']['error'] === UPLOAD_ERR_OK) {
    $zonesJson = file_get_contents($_FILES['zones']['tmp_name']);
}

// Save zones if found
if ($zonesJson) {
    $zonesPath = $uploadsDir . DIRECTORY_SEPARATOR . $timestamp . '_zones.json';
    file_put_contents($zonesPath, $zonesJson);
    $zonesArg = ' --zones ' . escapeshellarg($zonesPath);
}

////////////////////////////////////////////////////
// Python Command Builder
////////////////////////////////////////////////////

// Select Python executable
$python_env = getenv('PYTHON_EXEC');
if ($python_env && file_exists($python_env)) {
    $python = $python_env;
} else {
    $python = 'C:\\Users\\sreeg\\AppData\\Local\\Programs\\Python\\Python313\\python.exe';
    if (!file_exists($python)) $python = 'python';
}

$script = escapeshellarg(__DIR__ . DIRECTORY_SEPARATOR . 'yolo_runner.py');
$input = escapeshellarg($targetPath);
$out = escapeshellarg($outputsDir);

$cmd = escapeshellarg($python) . " $script --input $input --output_dir $out" . $zonesArg . " 2>&1";

exec($cmd, $outputLines, $returnVar);
$outputText = implode("\n", $outputLines);

////////////////////////////////////////////////////
// Error Handling
////////////////////////////////////////////////////
if ($returnVar !== 0) {
    echo json_encode([
        'success' => false,
        'message' => 'Python failed',
        'debug' => $outputText
    ]);
    exit;
}

// Last line from python expected to be JSON
$lastLine = end($outputLines);
$result = json_decode($lastLine, true);

////////////////////////////////////////////////////
// Build Frontend URL for Annotated Output
////////////////////////////////////////////////////
if ($result && isset($result['annotated_path'])) {
    $annotPath = $result['annotated_path'];

    $docRoot = realpath($_SERVER['DOCUMENT_ROOT']);
    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $host = $_SERVER['HTTP_HOST'] ?? ($_SERVER['SERVER_NAME'] ?? 'localhost');

    $relUrl = null;

    if ($docRoot !== false && strpos(realpath($annotPath), $docRoot) === 0) {
        $relUrl = str_replace('\\', '/', substr(realpath($annotPath), strlen($docRoot)));
        $relUrl = '/' . ltrim($relUrl, '/');
    }

    $fullUrl = $relUrl ? ($scheme . '://' . $host . $relUrl) : $annotPath;

    echo json_encode([
        'success' => true,
        'message' => 'Processed successfully',
        'output_url' => $fullUrl,
        'meta' => $result
    ]);
    exit;
}

// No JSON returned by python
echo json_encode([
    'success' => true,
    'message' => 'Processed but no meta found',
    'debug' => $outputText
]);
