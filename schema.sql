-- Create table for top-level daily statistics
CREATE TABLE IF NOT EXISTS daily_reports (
    report_date DATE PRIMARY KEY,
    time_hrs VARCHAR(50),
    frequency_hz DECIMAL,
    total_capacity_mw DECIMAL,
    total_lighting_peak_mw DECIMAL,
    total_minimum_load_mw DECIMAL,
    total_morning_peak_mw DECIMAL,
    total_consumption_mu DECIMAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create table for line-item generation details
CREATE TABLE IF NOT EXISTS generation_details (
    report_date DATE REFERENCES daily_reports(report_date) ON DELETE CASCADE,
    category VARCHAR(255),
    capacity_mw DECIMAL,
    lighting_peak_mw DECIMAL,
    minimum_load_mw DECIMAL,
    morning_peak_mw DECIMAL,
    consumption_mu DECIMAL,
    PRIMARY KEY (report_date, category)
);
