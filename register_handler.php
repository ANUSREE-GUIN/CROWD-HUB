<?php
// Set Content-Type header to ensure the response is treated as plain text by AJAX
header('Content-Type: text/plain'); 

// --- CONFIGURATION: REPLACE THESE WITH YOUR ACTUAL DETAILS ---
define('DB_SERVER', 'localhost');
define('DB_USERNAME', 'root'); // <-- Use 'root' or your actual DB user
define('DB_PASSWORD', '');     // <-- Use '' (empty) or your actual password
define('DB_NAME', 'user');     // <-- Use your actual database name (e.g., 'user')
// -----------------------------------------------------------

// 1. Check if the form was submitted via POST
if ($_SERVER["REQUEST_METHOD"] != "POST") {
    // If accessed directly, send a clear error message
    echo "ERROR: Invalid request method."; 
    exit();
}

// 2. Establish Database Connection
$mysqli = new mysqli(DB_SERVER, DB_USERNAME, DB_PASSWORD, DB_NAME);

// Check connection
if ($mysqli->connect_error) {
    // Use 'echo' to send the error text back to the AJAX call
    echo "ERROR: Could not connect to database. Check credentials and server status.";
    exit();
}

// 3. Retrieve Data using the EXACT field names from the HTML
$fullName = trim($_POST['fullName']);
$email = trim($_POST['email']);
$password = $_POST['password']; 
$phone = trim($_POST['phone']); 
$gender = $_POST['gender']; 

// 4. Server-Side Validation (Minimal)
if (empty($fullName) || empty($email) || empty($password) || empty($gender)) {
    $mysqli->close();
    echo "ERROR: Missing required fields. Please fill out the form completely.";
    exit();
}

// 5. Securely Hash the Password
$password_hash = password_hash($password, PASSWORD_DEFAULT);

// Clean up the phone number: If empty, set it to NULL for the database.
// MySQLi's bind_param handles NULL values correctly if you pass the PHP null.
$phone_number_to_store = !empty($phone) ? $phone : null;

// 6. SQL Query using Prepared Statements
// Column names must match your MySQL table exactly (user table structure from previous reply)
$sql = "INSERT INTO users (full_name, email, password_hash, phone, gender) 
        VALUES (?, ?, ?, ?, ?)"; 
        
// NOTE: I changed the table name to 'users' and column names to lower_snake_case 
// based on standard practice and the SQL code provided previously. 
// IF YOUR TABLE/COLUMNS USE CAPITALIZATION (e.g. 'user', 'Full_Name'), 
// YOU MUST CHANGE THE SQL ABOVE BACK TO MATCH YOUR EXACT TABLE DEFINITION!

if ($stmt = $mysqli->prepare($sql)) {
    
    // Bind parameters: 'sssss' means 5 string parameters
    // We bind $phone_number_to_store as a string even if it's PHP null,
    // which mysqli handles for INSERT statements into NULLable columns.
    $stmt->bind_param("sssss", 
        $fullName, 
        $email, 
        $password_hash, 
        $phone_number_to_store, 
        $gender
    );

    // 7. Execute the statement
    if ($stmt->execute()) {
        // SUCCESS! Send a text signal back to the JavaScript.
        echo "SUCCESS: User registered successfully.";
    } else {
        // Handle execution errors (e.g., duplicate email constraint failure)
        if ($mysqli->errno == 1062) { 
            echo "ERROR: This email address is already registered.";
        } else {
            // General database error
            echo "ERROR: Could not complete registration. Database error.";
        }
    }

    // Close statement
    $stmt->close();
} else {
    // Error in preparing the statement (usually a typo in the SQL string)
    echo "ERROR: Database query preparation failed. Check your SQL syntax and table/column names.";
}

// Close connection
$mysqli->close();
?>