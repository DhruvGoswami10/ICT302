<?php
// Scheduled "weekly risk scan" task definition.
defined('MOODLE_INTERNAL') || die();

$tasks = [
    [
        'classname' => 'report_smartdashboard\task\risk_scan',
        'blocking'  => 0,
        // Weekly, Sunday 03:00 — the "weekend scan".
        'minute'    => '0',
        'hour'      => '3',
        'day'       => '*',
        'dayofweek' => '0',
        'month'     => '*',
    ],
];
