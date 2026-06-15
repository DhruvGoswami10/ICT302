<?php
namespace report_smartdashboard\task;

defined('MOODLE_INTERNAL') || die();

/**
 * Weekly AI risk scan: re-runs the scikit-learn scorer over current Moodle
 * activity, refreshing the engagement + at-risk data the dashboard reads.
 */
class risk_scan extends \core\task\scheduled_task {

    public function get_name() {
        return get_string('taskriskscan', 'report_smartdashboard');
    }

    public function execute() {
        $python = get_config('report_smartdashboard', 'pythonpath');
        $scorer = get_config('report_smartdashboard', 'scorerpath');
        if (empty($python)) {
            $python = '/home/td05/ict302/venv/bin/python';
        }
        if (empty($scorer)) {
            $scorer = '/home/td05/ict302/ml/score_moodle.py';
        }
        if (!is_file($scorer)) {
            mtrace("Smart LMS: scorer not found at $scorer");
            return;
        }
        $cmd = escapeshellarg($python) . ' ' . escapeshellarg($scorer) . ' 2>&1';
        mtrace("Smart LMS: running risk scan -> $cmd");
        $output = shell_exec($cmd);
        mtrace("Smart LMS: " . trim((string)$output));
    }
}
