-- ============================================================
--  StudentBase — Live Attendance & Monitoring System
--  Database Schema
-- ============================================================

CREATE DATABASE IF NOT EXISTS studentbase CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE studentbase;

-- ── Users (Admin + Students login) ──────────────────────────
CREATE TABLE IF NOT EXISTS sqlusers (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(80)  NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL,
    role        ENUM('admin','student') NOT NULL DEFAULT 'student',
    student_id  INT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Students ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS students (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    student_number  VARCHAR(20)  NOT NULL UNIQUE,
    first_name      VARCHAR(80)  NOT NULL,
    last_name       VARCHAR(80)  NOT NULL,
    email           VARCHAR(120) NOT NULL UNIQUE,
    course          VARCHAR(100) DEFAULT '',
    year_level      INT DEFAULT 1,
    section         VARCHAR(20)  DEFAULT '',
    qr_token        VARCHAR(64)  NOT NULL UNIQUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Attendance ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS attendance (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    student_id  INT NOT NULL,
    date        DATE NOT NULL,
    status      ENUM('Present','Absent','Late') NOT NULL DEFAULT 'Absent',
    scanned_at  DATETIME NULL,
    notes       VARCHAR(255) DEFAULT '',
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    UNIQUE KEY uq_student_date (student_id, date)
);

-- ── Notifications ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    message     VARCHAR(500) NOT NULL,
    type        ENUM('info','warning','danger') NOT NULL DEFAULT 'info',
    is_read     TINYINT(1) DEFAULT 0,
    student_id  INT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE SET NULL
);

-- ============================================================
--  Seed Data
-- ============================================================

-- Admin account  (password: admin123)
INSERT INTO sqlusers (username, password, role) VALUES
('admin', 'admin123', 'admin')
ON DUPLICATE KEY UPDATE id=id;

-- Sample students
INSERT INTO students (student_number, first_name, last_name, email, course, year_level, section, qr_token) VALUES
('2024-0001', 'Juan',         'dela Cruz', 'juan@school.edu',         'BSIT', 2, 'A', 'TOKEN_JUAN_001'),
('2024-0002', 'Maria',        'Santos',    'maria@school.edu',        'BSIT', 2, 'A', 'TOKEN_MARIA_002'),
('2024-0003', 'Raffy',        'Gepilgon',  'raffy@school.edu',        'BSCS', 3, 'B', 'TOKEN_RAFFY_003'),
('2024-0004', 'Rayvhen',      'Muñoz',     'rayvhen@school.edu',      'BSCS', 3, 'B', 'TOKEN_RAYVHEN_004'),
('2024-0005', 'Kyle Stephen', 'Tandang',   'kyle@school.edu',         'BSIT', 1, 'C', 'TOKEN_KYLE_005'),
('2024-0006', 'Cyril',        'Sumipo',    'cyril@school.edu',        'BSIT', 1, 'C', 'TOKEN_CYRIL_006'),
('2024-0007', 'Nile',         'Torres',    'nile@school.edu',         'BSIT', 1, 'C', 'TOKEN_NILE_007')
ON DUPLICATE KEY UPDATE id=id;

-- Student login accounts (password matches student_number)
INSERT INTO sqlusers (username, password, role, student_id)
SELECT s.student_number, s.student_number, 'student', s.id
FROM students s
ON DUPLICATE KEY UPDATE student_id = s.id;

-- Sample attendance (last 7 days)
INSERT IGNORE INTO attendance (student_id, date, status, scanned_at) VALUES
-- Juan: mostly present
(1, CURDATE() - INTERVAL 6 DAY, 'Present', NOW() - INTERVAL 6 DAY),
(1, CURDATE() - INTERVAL 5 DAY, 'Present', NOW() - INTERVAL 5 DAY),
(1, CURDATE() - INTERVAL 4 DAY, 'Late',    NOW() - INTERVAL 4 DAY),
(1, CURDATE() - INTERVAL 3 DAY, 'Present', NOW() - INTERVAL 3 DAY),
(1, CURDATE() - INTERVAL 2 DAY, 'Present', NOW() - INTERVAL 2 DAY),
(1, CURDATE() - INTERVAL 1 DAY, 'Absent',  NULL),
-- Maria: 3 consecutive absences (AT RISK)
(2, CURDATE() - INTERVAL 6 DAY, 'Present', NOW() - INTERVAL 6 DAY),
(2, CURDATE() - INTERVAL 5 DAY, 'Absent',  NULL),
(2, CURDATE() - INTERVAL 4 DAY, 'Absent',  NULL),
(2, CURDATE() - INTERVAL 3 DAY, 'Absent',  NULL),
(2, CURDATE() - INTERVAL 2 DAY, 'Absent',  NULL),
(2, CURDATE() - INTERVAL 1 DAY, 'Absent',  NULL),
-- Raffy Gepilgon: spotty attendance
(3, CURDATE() - INTERVAL 6 DAY, 'Absent',  NULL),
(3, CURDATE() - INTERVAL 5 DAY, 'Absent',  NULL),
(3, CURDATE() - INTERVAL 4 DAY, 'Present', NOW() - INTERVAL 4 DAY),
(3, CURDATE() - INTERVAL 3 DAY, 'Absent',  NULL),
(3, CURDATE() - INTERVAL 2 DAY, 'Absent',  NULL),
(3, CURDATE() - INTERVAL 1 DAY, 'Absent',  NULL),
-- Rayvhen Muñoz: good attendance
(4, CURDATE() - INTERVAL 6 DAY, 'Present', NOW() - INTERVAL 6 DAY),
(4, CURDATE() - INTERVAL 5 DAY, 'Present', NOW() - INTERVAL 5 DAY),
(4, CURDATE() - INTERVAL 4 DAY, 'Present', NOW() - INTERVAL 4 DAY),
(4, CURDATE() - INTERVAL 3 DAY, 'Late',    NOW() - INTERVAL 3 DAY),
(4, CURDATE() - INTERVAL 2 DAY, 'Present', NOW() - INTERVAL 2 DAY),
(4, CURDATE() - INTERVAL 1 DAY, 'Present', NOW() - INTERVAL 1 DAY),
-- Kyle Stephen Tandang: mixed
(5, CURDATE() - INTERVAL 6 DAY, 'Present', NOW() - INTERVAL 6 DAY),
(5, CURDATE() - INTERVAL 5 DAY, 'Late',    NOW() - INTERVAL 5 DAY),
(5, CURDATE() - INTERVAL 4 DAY, 'Absent',  NULL),
(5, CURDATE() - INTERVAL 3 DAY, 'Present', NOW() - INTERVAL 3 DAY),
(5, CURDATE() - INTERVAL 2 DAY, 'Absent',  NULL),
(5, CURDATE() - INTERVAL 1 DAY, 'Present', NOW() - INTERVAL 1 DAY),
-- Cyril Sumipo: mostly present
(6, CURDATE() - INTERVAL 6 DAY, 'Present', NOW() - INTERVAL 6 DAY),
(6, CURDATE() - INTERVAL 5 DAY, 'Present', NOW() - INTERVAL 5 DAY),
(6, CURDATE() - INTERVAL 4 DAY, 'Late',    NOW() - INTERVAL 4 DAY),
(6, CURDATE() - INTERVAL 3 DAY, 'Present', NOW() - INTERVAL 3 DAY),
(6, CURDATE() - INTERVAL 2 DAY, 'Present', NOW() - INTERVAL 2 DAY),
(6, CURDATE() - INTERVAL 1 DAY, 'Present', NOW() - INTERVAL 1 DAY),
-- Nile Torres: mostly present
(7, CURDATE() - INTERVAL 6 DAY, 'Present', NOW() - INTERVAL 6 DAY),
(7, CURDATE() - INTERVAL 5 DAY, 'Late',    NOW() - INTERVAL 5 DAY),
(7, CURDATE() - INTERVAL 4 DAY, 'Present', NOW() - INTERVAL 4 DAY),
(7, CURDATE() - INTERVAL 3 DAY, 'Absent',  NULL),
(7, CURDATE() - INTERVAL 2 DAY, 'Present', NOW() - INTERVAL 2 DAY),
(7, CURDATE() - INTERVAL 1 DAY, 'Present', NOW() - INTERVAL 1 DAY);