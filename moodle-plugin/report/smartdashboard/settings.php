<?php
defined('MOODLE_INTERNAL') || die();

if ($hassiteconfig) {
    $settings = new admin_settingpage('report_smartdashboard',
        get_string('pluginname', 'report_smartdashboard'));

    $settings->add(new admin_setting_configtext('report_smartdashboard/dashboardurl',
        get_string('dashboardurl', 'report_smartdashboard'),
        get_string('dashboardurl_desc', 'report_smartdashboard'),
        'http://10.51.33.70/', PARAM_URL));

    $settings->add(new admin_setting_configtext('report_smartdashboard/pythonpath',
        get_string('pythonpath', 'report_smartdashboard'),
        get_string('pythonpath_desc', 'report_smartdashboard'),
        '/home/td05/ict302/venv/bin/python', PARAM_RAW));

    $settings->add(new admin_setting_configtext('report_smartdashboard/scorerpath',
        get_string('scorerpath', 'report_smartdashboard'),
        get_string('scorerpath_desc', 'report_smartdashboard'),
        '/home/td05/ict302/ml/score_moodle.py', PARAM_RAW));

    $settings->add(new admin_setting_configtext('report_smartdashboard/riskjson',
        get_string('riskjson', 'report_smartdashboard'),
        get_string('riskjson_desc', 'report_smartdashboard'),
        '/home/td05/ict302/ml/models/live_risk.json', PARAM_RAW));

    $ADMIN->add('reports', $settings);
}
