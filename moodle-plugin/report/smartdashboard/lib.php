<?php
// Navigation integration: add the report to a course's Reports menu.
defined('MOODLE_INTERNAL') || die();

/**
 * Add "Smart LMS Dashboard" to the course navigation (Reports).
 *
 * @param navigation_node $navigation
 * @param stdClass $course
 * @param context_course $context
 */
function report_smartdashboard_extend_navigation_course($navigation, $course, $context) {
    if (has_capability('report/smartdashboard:view', $context)) {
        $url = new moodle_url('/report/smartdashboard/index.php', ['id' => $course->id]);
        $navigation->add(
            get_string('pluginname', 'report_smartdashboard'),
            $url,
            navigation_node::TYPE_SETTING,
            null,
            'report_smartdashboard',
            new pix_icon('i/report', '')
        );
    }
}

/**
 * Map this report into the standard "course reports" list.
 */
function report_smartdashboard_get_course_reports() {
    return ['smartdashboard' => get_string('pluginname', 'report_smartdashboard')];
}
