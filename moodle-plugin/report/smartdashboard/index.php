<?php
// Smart LMS Dashboard - course report page for the Unit Coordinator.
require('../../config.php');
require_once($CFG->dirroot . '/lib/tablelib.php');

$id = required_param('id', PARAM_INT); // course id
$runscan = optional_param('runscan', 0, PARAM_INT);

$course = $DB->get_record('course', ['id' => $id], '*', MUST_EXIST);
require_login($course);
$context = context_course::instance($course->id);
require_capability('report/smartdashboard:view', $context);

$PAGE->set_url('/report/smartdashboard/index.php', ['id' => $id]);
$PAGE->set_context($context);
$PAGE->set_pagelayout('report');
$PAGE->set_title(get_string('pluginname', 'report_smartdashboard'));
$PAGE->set_heading($course->fullname);

// Optionally trigger an on-demand AI risk scan.
if ($runscan && confirm_sesskey() && has_capability('moodle/site:config', context_system::instance())) {
    $task = new \report_smartdashboard\task\risk_scan();
    $task->execute();
    redirect($PAGE->url, 'AI risk scan complete.', 2);
}

// ---- AI risk data (from the scikit-learn scorer) ----
$riskfile = get_config('report_smartdashboard', 'riskjson');
if (empty($riskfile)) {
    $riskfile = '/home/td05/ict302/ml/models/live_risk.json';
}
$riskbysid = [];
if (is_readable($riskfile)) {
    $data = json_decode(file_get_contents($riskfile), true);
    foreach ((array)$data as $r) {
        $riskbysid[(int)$r['sid']] = $r;
    }
}

// ---- Engagement computed live from the standard log store ----
$weights = "CASE
    WHEN l.component LIKE '%assign%' OR l.component LIKE '%quiz%' THEN 3
    WHEN l.component LIKE '%forum%' THEN 2
    WHEN l.component LIKE '%resource%' OR l.component LIKE '%url%' OR l.component LIKE '%page%' THEN 1.2
    ELSE 1 END";
$sql = "SELECT u.id, u.username, u.firstname, u.lastname,
               COUNT(l.id) AS events,
               COALESCE(SUM($weights),0) AS weighted,
               COUNT(DISTINCT FLOOR(l.timecreated/604800)) AS activeweeks,
               MAX(l.timecreated) AS lastaccess
        FROM {user} u
        JOIN {user_enrolments} ue ON ue.userid = u.id
        JOIN {enrol} e ON e.id = ue.enrolid AND e.courseid = :cid1
        JOIN {role_assignments} ra ON ra.userid = u.id
        JOIN {context} ctx ON ctx.id = ra.contextid AND ctx.contextlevel = 50 AND ctx.instanceid = :cid2
        LEFT JOIN {logstore_standard_log} l ON l.userid = u.id AND l.courseid = :cid3
        WHERE ra.roleid = 5
        GROUP BY u.id, u.username, u.firstname, u.lastname
        ORDER BY weighted ASC";
$rows = $DB->get_records_sql($sql, ['cid1' => $id, 'cid2' => $id, 'cid3' => $id]);

$maxw = 1;
foreach ($rows as $r) {
    $maxw = max($maxw, (float)$r->weighted);
}

echo $OUTPUT->header();
echo $OUTPUT->heading(get_string('heading', 'report_smartdashboard'));

// Summary line.
$total = count($rows);
$high = $med = 0;
$engsum = 0;
foreach ($rows as $r) {
    $sid = (int)preg_replace('/\D/', '', $r->username);
    $eng = round(100 * ((float)$r->weighted) / $maxw, 1);
    $engsum += $eng;
    $band = isset($riskbysid[$sid]) ? $riskbysid[$sid]['risk_band'] : 'Low';
    if ($band === 'High') $high++;
    if ($band === 'Medium') $med++;
}
$a = (object)['total' => $total, 'high' => $high, 'medium' => $med,
              'eng' => $total ? round($engsum / $total, 1) : 0];
echo html_writer::div(get_string('summary', 'report_smartdashboard', $a),
    'alert alert-info');

// Action buttons.
$dashurl = get_config('report_smartdashboard', 'dashboardurl') ?: 'http://10.51.33.70/';
echo html_writer::start_div('mb-3');
echo html_writer::link($dashurl, get_string('openfull', 'report_smartdashboard'),
    ['class' => 'btn btn-primary', 'target' => '_blank']);
if (has_capability('moodle/site:config', context_system::instance())) {
    echo ' ' . html_writer::link(
        new moodle_url($PAGE->url, ['runscan' => 1, 'sesskey' => sesskey()]),
        get_string('runscan', 'report_smartdashboard'), ['class' => 'btn btn-secondary']);
}
echo html_writer::end_div();

// Student table.
$table = new html_table();
$table->head = [
    get_string('student', 'report_smartdashboard'),
    get_string('engagement', 'report_smartdashboard'),
    get_string('events', 'report_smartdashboard'),
    get_string('activeweeks', 'report_smartdashboard'),
    get_string('risk', 'report_smartdashboard'),
    get_string('band', 'report_smartdashboard'),
    get_string('lastaccess', 'report_smartdashboard'),
];
$table->attributes['class'] = 'generaltable';

foreach ($rows as $r) {
    $sid = (int)preg_replace('/\D/', '', $r->username);
    $eng = round(100 * ((float)$r->weighted) / $maxw, 1);
    $risk = isset($riskbysid[$sid]) ? $riskbysid[$sid] : null;
    $prob = $risk ? round($risk['risk_prob'] * 100) . '%' : '–';
    $band = $risk ? $risk['risk_band'] : 'Low';
    $colour = ['High' => '#ef4444', 'Medium' => '#f59e0b', 'Low' => '#22c55e'][$band];
    $badge = html_writer::tag('span', $band,
        ['style' => "background:$colour;color:#fff;padding:2px 9px;border-radius:10px;font-size:11px"]);
    $barpct = min(100, $eng);
    $bar = html_writer::div(
        html_writer::div('', '', ['style' => "width:{$barpct}%;height:8px;background:#38bdf8;border-radius:4px"]),
        '', ['style' => 'background:#e2e8f0;border-radius:4px;width:90px;display:inline-block;margin-right:6px']
    ) . $eng;
    $last = $r->lastaccess ? userdate($r->lastaccess, '%d %b %H:%M') : '—';
    $name = html_writer::link(
        new moodle_url('/user/view.php', ['id' => $r->id, 'course' => $id]),
        $r->firstname . ' ' . $r->lastname);
    $table->data[] = [$name, $bar, (int)$r->events, (int)$r->activeweeks, $prob, $badge, $last];
}
echo html_writer::table($table);

// Embedded live dashboard.
echo $OUTPUT->heading('Live dashboard', 4);
echo html_writer::tag('iframe', '', [
    'src' => $dashurl, 'width' => '100%', 'height' => '900',
    'style' => 'border:1px solid #ccc;border-radius:8px']);

echo $OUTPUT->footer();
