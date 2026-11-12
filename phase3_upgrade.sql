
-- ============================================================
-- DEMAND PREDICTION AND RESOURCE OPTIMIZATION
-- PHASE 3 DATABASE UPGRADE
-- MySQL 8.0+
-- ============================================================

USE demand_prediction_db;


-- ============================================================
-- 1. INGREDIENTS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS ingredients (
    ingredient_id INT AUTO_INCREMENT PRIMARY KEY,
    ingredient_name VARCHAR(100) NOT NULL UNIQUE,
    unit VARCHAR(20) NOT NULL DEFAULT 'kg',
    reorder_level DECIMAL(10,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CHECK (reorder_level >= 0)
) ENGINE=InnoDB;


-- ============================================================
-- 2. INVENTORY TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id INT AUTO_INCREMENT PRIMARY KEY,
    ingredient_id INT NOT NULL,
    quantity DECIMAL(10,2) NOT NULL DEFAULT 0,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_inventory_ingredient (ingredient_id),

    CONSTRAINT fk_inventory_ingredient
        FOREIGN KEY (ingredient_id)
        REFERENCES ingredients(ingredient_id)
        ON DELETE RESTRICT,

    CHECK (quantity >= 0)
) ENGINE=InnoDB;


-- ============================================================
-- 3. DONATION REQUESTS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS donation_requests (
    donation_id INT AUTO_INCREMENT PRIMARY KEY,

    surplus_id INT NOT NULL,
    facility_id INT NULL,

    requested_quantity INT NOT NULL,

    status ENUM(
        'Requested',
        'Accepted',
        'Rejected',
        'Pickup Scheduled',
        'Collected',
        'Cancelled'
    ) NOT NULL DEFAULT 'Requested',

    pickup_time DATETIME NULL,
    notes VARCHAR(255) NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_donation_surplus
        FOREIGN KEY (surplus_id)
        REFERENCES surplus_records(surplus_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_donation_facility
        FOREIGN KEY (facility_id)
        REFERENCES facilities(facility_id)
        ON DELETE SET NULL,

    CHECK (requested_quantity > 0)
) ENGINE=InnoDB;


-- ============================================================
-- 4. AUDIT LOGS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,

    entity_type VARCHAR(50) NOT NULL,
    entity_id INT NULL,
    action_type VARCHAR(20) NOT NULL,
    details VARCHAR(500) NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_audit_created (created_at),
    INDEX idx_audit_entity (entity_type, entity_id)
) ENGINE=InnoDB;


-- ============================================================
-- 5. FOOD WASTE SUMMARY VIEW
-- ============================================================

CREATE OR REPLACE VIEW v_food_waste_summary AS

SELECT
    f.item_id,
    f.item_name,

    COALESCE(SUM(d.prepared_qty), 0)
        AS total_prepared,

    COALESCE(SUM(d.sold_qty), 0)
        AS total_sold,

    COALESCE(SUM(d.leftover_qty), 0)
        AS total_leftover,

    COALESCE(
        SUM(d.leftover_qty * f.production_cost), 0
    ) AS waste_cost

FROM food_items f

LEFT JOIN daily_records d
    ON d.item_id = f.item_id

GROUP BY
    f.item_id,
    f.item_name;


-- ============================================================
-- 6. PERFORMANCE INDEXES
-- ============================================================

CREATE INDEX idx_daily_date
    ON daily_records(record_date);

CREATE INDEX idx_surplus_status
    ON surplus_records(status);

CREATE INDEX idx_predictions_date
    ON predictions(prediction_date);


-- ============================================================
-- 7. INVENTORY AUDIT TRIGGER
-- ============================================================

DELIMITER //

DROP TRIGGER IF EXISTS trg_inventory_audit_update//

CREATE TRIGGER trg_inventory_audit_update

AFTER UPDATE ON inventory

FOR EACH ROW

BEGIN

    INSERT INTO audit_logs (
        entity_type,
        entity_id,
        action_type,
        details
    )

    VALUES (
        'inventory',
        NEW.inventory_id,
        'UPDATE',

        CONCAT(
            'Stock changed from ',
            OLD.quantity,
            ' to ',
            NEW.quantity,
            ' ',
            (
                SELECT unit
                FROM ingredients
                WHERE ingredient_id = NEW.ingredient_id
            )
        )
    );

END//

DELIMITER ;


-- ============================================================
-- PHASE 3 DATABASE UPGRADE COMPLETED
-- ============================================================
