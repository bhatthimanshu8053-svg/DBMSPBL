
-- =====================================================================
-- Demand Prediction and Resource Optimization
-- Phase 2 Database Schema
-- =====================================================================

CREATE DATABASE IF NOT EXISTS demand_prediction_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE demand_prediction_db;

-- Drop child tables first
DROP TABLE IF EXISTS surplus_records;
DROP TABLE IF EXISTS storage_records;
DROP TABLE IF EXISTS predictions;
DROP TABLE IF EXISTS daily_records;
DROP TABLE IF EXISTS facilities;
DROP TABLE IF EXISTS food_items;

-- 1. Food Items
CREATE TABLE food_items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    item_name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL,
    selling_price DECIMAL(8,2) NOT NULL,
    production_cost DECIMAL(8,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_selling_price CHECK (selling_price > 0),
    CONSTRAINT chk_production_cost CHECK (production_cost >= 0)
) ENGINE=InnoDB;

-- 2. Daily Records
CREATE TABLE daily_records (
    record_id INT AUTO_INCREMENT PRIMARY KEY,
    record_date DATE NOT NULL,
    item_id INT NOT NULL,
    prepared_qty INT NOT NULL,
    sold_qty INT NOT NULL,
    leftover_qty INT GENERATED ALWAYS AS
        (prepared_qty - sold_qty) STORED,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_item_date UNIQUE (item_id, record_date),
    CONSTRAINT fk_daily_item FOREIGN KEY (item_id)
        REFERENCES food_items(item_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT chk_prepared_pos CHECK (prepared_qty > 0),
    CONSTRAINT chk_sold_not_neg CHECK (sold_qty >= 0),
    CONSTRAINT chk_sold_le_prep CHECK (sold_qty <= prepared_qty)
) ENGINE=InnoDB;

-- 3. Predictions
CREATE TABLE predictions (
    prediction_id INT AUTO_INCREMENT PRIMARY KEY,
    item_id INT NOT NULL,
    prediction_date DATE NOT NULL,
    records_used INT NOT NULL,
    avg_sales DECIMAL(10,2) NOT NULL,
    buffer_percent DECIMAL(5,2) NOT NULL DEFAULT 5.00,
    recommended_qty INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pred_item FOREIGN KEY (item_id)
        REFERENCES food_items(item_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_records_used CHECK (records_used BETWEEN 1 AND 7),
    CONSTRAINT chk_avg_sales CHECK (avg_sales >= 0),
    CONSTRAINT chk_recommended CHECK (recommended_qty >= 0)
) ENGINE=InnoDB;

-- 4. Facilities
CREATE TABLE facilities (
    facility_id INT AUTO_INCREMENT PRIMARY KEY,
    facility_name VARCHAR(120) NOT NULL,
    facility_type ENUM(
        'Donation Centre',
        'Composting Facility'
    ) NOT NULL,
    address VARCHAR(255) NOT NULL,
    accepted_material VARCHAR(255) NOT NULL,
    contact VARCHAR(100) NOT NULL,
    is_sample TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB;

-- 5. Surplus Records
CREATE TABLE surplus_records (
    surplus_id INT AUTO_INCREMENT PRIMARY KEY,
    record_id INT NOT NULL,
    facility_id INT NULL,
    quantity INT NOT NULL,
    status ENUM(
        'Available',
        'Donated',
        'Composted',
        'Discarded'
    ) NOT NULL DEFAULT 'Available',
    notes VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_surplus_record FOREIGN KEY (record_id)
        REFERENCES daily_records(record_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_surplus_facility FOREIGN KEY (facility_id)
        REFERENCES facilities(facility_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT chk_surplus_qty CHECK (quantity > 0)
) ENGINE=InnoDB;

-- 6. Storage Records
CREATE TABLE storage_records (
    storage_id INT AUTO_INCREMENT PRIMARY KEY,
    item_id INT NOT NULL,
    prep_time DATETIME NOT NULL,
    storage_method ENUM(
        'Room Temperature',
        'Refrigerated',
        'Hot Holding',
        'Frozen'
    ) NOT NULL,
    temperature_c DECIMAL(5,1) NULL,
    notes VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_storage_item FOREIGN KEY (item_id)
        REFERENCES food_items(item_id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- =====================================================================
-- SAMPLE DATA
-- =====================================================================

INSERT INTO food_items
(item_name, category, selling_price, production_cost)
VALUES
('Veg Biryani', 'Main Course', 60.00, 35.00),
('Samosa', 'Snacks', 15.00, 8.00),
('Masala Dosa', 'Breakfast', 45.00, 25.00),
('Chole Bhature', 'Main Course', 55.00, 30.00),
('Tea', 'Beverages', 10.00, 4.00);

-- Daily Records
INSERT INTO daily_records
(record_date, item_id, prepared_qty, sold_qty)
VALUES
(DATE_SUB(CURDATE(), INTERVAL 8 DAY), 1, 100, 88),
(DATE_SUB(CURDATE(), INTERVAL 7 DAY), 1, 100, 92),
(DATE_SUB(CURDATE(), INTERVAL 6 DAY), 1, 110, 95),
(DATE_SUB(CURDATE(), INTERVAL 5 DAY), 1, 100, 85),
(DATE_SUB(CURDATE(), INTERVAL 4 DAY), 1, 105, 98),
(DATE_SUB(CURDATE(), INTERVAL 3 DAY), 1, 100, 90),
(DATE_SUB(CURDATE(), INTERVAL 2 DAY), 1, 110, 101),
(DATE_SUB(CURDATE(), INTERVAL 1 DAY), 1, 100, 94),

(DATE_SUB(CURDATE(), INTERVAL 8 DAY), 2, 200, 178),
(DATE_SUB(CURDATE(), INTERVAL 7 DAY), 2, 200, 185),
(DATE_SUB(CURDATE(), INTERVAL 6 DAY), 2, 220, 190),
(DATE_SUB(CURDATE(), INTERVAL 5 DAY), 2, 200, 170),
(DATE_SUB(CURDATE(), INTERVAL 4 DAY), 2, 210, 196),
(DATE_SUB(CURDATE(), INTERVAL 3 DAY), 2, 200, 182),
(DATE_SUB(CURDATE(), INTERVAL 2 DAY), 2, 220, 205),
(DATE_SUB(CURDATE(), INTERVAL 1 DAY), 2, 200, 188),

(DATE_SUB(CURDATE(), INTERVAL 8 DAY), 3, 80, 70),
(DATE_SUB(CURDATE(), INTERVAL 7 DAY), 3, 80, 74),
(DATE_SUB(CURDATE(), INTERVAL 6 DAY), 3, 90, 72),
(DATE_SUB(CURDATE(), INTERVAL 5 DAY), 3, 80, 68),
(DATE_SUB(CURDATE(), INTERVAL 4 DAY), 3, 85, 79),
(DATE_SUB(CURDATE(), INTERVAL 3 DAY), 3, 80, 71),
(DATE_SUB(CURDATE(), INTERVAL 2 DAY), 3, 90, 82),
(DATE_SUB(CURDATE(), INTERVAL 1 DAY), 3, 80, 75),

(DATE_SUB(CURDATE(), INTERVAL 8 DAY), 4, 90, 70),
(DATE_SUB(CURDATE(), INTERVAL 7 DAY), 4, 90, 76),
(DATE_SUB(CURDATE(), INTERVAL 6 DAY), 4, 100, 78),
(DATE_SUB(CURDATE(), INTERVAL 5 DAY), 4, 90, 69),
(DATE_SUB(CURDATE(), INTERVAL 4 DAY), 4, 95, 80),
(DATE_SUB(CURDATE(), INTERVAL 3 DAY), 4, 90, 72),
(DATE_SUB(CURDATE(), INTERVAL 2 DAY), 4, 100, 83),
(DATE_SUB(CURDATE(), INTERVAL 1 DAY), 4, 90, 74),

(DATE_SUB(CURDATE(), INTERVAL 8 DAY), 5, 300, 280),
(DATE_SUB(CURDATE(), INTERVAL 7 DAY), 5, 300, 290),
(DATE_SUB(CURDATE(), INTERVAL 6 DAY), 5, 320, 285),
(DATE_SUB(CURDATE(), INTERVAL 5 DAY), 5, 300, 270),
(DATE_SUB(CURDATE(), INTERVAL 4 DAY), 5, 310, 295),
(DATE_SUB(CURDATE(), INTERVAL 3 DAY), 5, 300, 282),
(DATE_SUB(CURDATE(), INTERVAL 2 DAY), 5, 320, 300),
(DATE_SUB(CURDATE(), INTERVAL 1 DAY), 5, 300, 288);

-- Sample Facilities
INSERT INTO facilities
(facility_name, facility_type, address,
 accepted_material, contact, is_sample)
VALUES
('Sample Donation Centre A (fictional)',
 'Donation Centre', 'Sample Address 1, Near Main Gate (placeholder)',
 'Packed cooked meals, bread, packaged snacks',
 'Phone: 000-000-0001 (sample)', 1),

('Sample Food Bank B (fictional)',
 'Donation Centre', 'Sample Address 2, City Road (placeholder)',
 'Dry ration, bread, fruits, sealed items',
 'Phone: 000-000-0002 (sample)', 1),

('Sample Community Kitchen C (fictional)',
 'Donation Centre', 'Sample Address 3, Market Area (placeholder)',
 'Freshly cooked vegetarian meals (same day)',
 'Email: kitchen-c@example.com (sample)', 1),

('Sample Compost Unit D (fictional)',
 'Composting Facility', 'Sample Address 4, Outskirts (placeholder)',
 'Vegetable peels, tea waste, spoiled cooked food',
 'Phone: 000-000-0004 (sample)', 1),

('Sample Bio-Compost Plant E (fictional)',
 'Composting Facility', 'Sample Address 5, Industrial Area (placeholder)',
 'Mixed food waste, fruit waste, leftover rice',
 'Email: compost-e@example.com (sample)', 1);

-- Sample Surplus
INSERT INTO surplus_records
(record_id, facility_id, quantity, status, notes)
VALUES
(8, 1, 6, 'Donated',
 'Sample entry - packed and handed over the same evening'),
(16, NULL, 12, 'Available',
 'Sample entry - waiting to be collected'),
(32, 4, 10, 'Composted',
 'Sample entry - spoiled portion sent for composting');

-- Sample Storage
INSERT INTO storage_records
(item_id, prep_time, storage_method, temperature_c, notes)
VALUES
(1, DATE_SUB(NOW(), INTERVAL 1 HOUR),
 'Hot Holding', 65.0, 'Steam counter - OK'),
(2, DATE_SUB(NOW(), INTERVAL 3 HOUR),
 'Room Temperature', NULL, 'Left on the serving counter'),
(4, DATE_SUB(NOW(), INTERVAL 5 HOUR),
 'Refrigerated', 8.0, 'Fridge was opened often'),
(3, DATE_SUB(NOW(), INTERVAL 30 HOUR),
 'Refrigerated', 4.0, 'Dosa batter kept in fridge');

