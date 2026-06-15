<?php
// CLI bootstrap script: builds the ICT001 course, UC (teacher) + student accounts,
// activities, and enrolments. Idempotent where practical. Run as www-data.
define('CLI_SCRIPT', true);
require('/var/www/html/moodle/config.php');
require_once($CFG->dirroot.'/user/lib.php');
require_once($CFG->dirroot.'/course/lib.php');
require_once($CFG->dirroot.'/course/modlib.php');
require_once($CFG->libdir.'/enrollib.php');
require_once($CFG->libdir.'/gradelib.php');

global $DB, $CFG;
$CFG->passwordpolicy = 0; // relax for demo accounts

function ensure_user($username, $first, $last, $email, $password) {
    global $DB, $CFG;
    if ($u = $DB->get_record('user', ['username'=>$username])) { return $u; }
    $user = new stdClass();
    $user->auth = 'manual';
    $user->confirmed = 1;
    $user->mnethostid = $CFG->mnet_localhost_id;
    $user->username = $username;
    $user->password = $password; // hashed by user_create_user
    $user->firstname = $first;
    $user->lastname = $last;
    $user->email = $email;
    $user->lang = 'en';
    $id = user_create_user($user, true, false);
    return $DB->get_record('user', ['id'=>$id]);
}

function role_id($shortname) {
    global $DB; return $DB->get_field('role', 'id', ['shortname'=>$shortname]);
}

function enrol_user_in($courseid, $userid, $roleshort) {
    global $DB;
    $instance = $DB->get_record('enrol', ['courseid'=>$courseid, 'enrol'=>'manual'], '*', IGNORE_MULTIPLE);
    if (!$instance) { return; }
    $plugin = enrol_get_plugin('manual');
    $plugin->enrol_user($instance, $userid, role_id($roleshort));
}

function add_activity($course, $modname, $section, $name, $intro, $extra=[]) {
    global $DB, $CFG;
    $module = $DB->get_record('modules', ['name'=>$modname], '*', MUST_EXIST);
    $mi = new stdClass();
    $mi->modulename = $modname;
    $mi->module = $module->id;
    $mi->course = $course->id;
    $mi->section = $section;
    $mi->visible = 1;
    $mi->visibleoncoursepage = 1;
    $mi->name = $name;
    $mi->intro = $intro;
    $mi->introformat = FORMAT_HTML;
    $mi->showdescription = 0;
    $mi->cmidnumber = '';
    // Completion / group / availability defaults normally supplied by the mod form.
    $mi->completion = 0;
    $mi->completionview = 0;
    $mi->completionexpected = 0;
    $mi->completiongradeitemnumber = null;
    $mi->groupmode = 0;
    $mi->groupingid = 0;
    $mi->availabilityconditionsjson = null;
    // Grading defaults (used by assign/quiz/forum).
    $mi->grade = 100;
    $mi->gradecat = 0;
    $mi->gradepass = 0;
    foreach ($extra as $k=>$v) { $mi->$k = $v; }
    $mi = add_moduleinfo($mi, $course);
    return $mi;
}

// ---- Category + Course ----
$catid = $DB->get_field('course_categories', 'id', ['name'=>'ICT']);
if (!$catid) {
    $cat = core_course_category::create(['name'=>'ICT', 'description'=>'ICT units']);
    $catid = $cat->id;
}

$course = $DB->get_record('course', ['shortname'=>'ICT001']);
if (!$course) {
    $data = new stdClass();
    $data->fullname = 'ICT001 Theory of Programming (S1, 2025)';
    $data->shortname = 'ICT001';
    $data->category = $catid;
    $data->format = 'topics';
    $data->numsections = 6;
    $data->summary = 'Smart LMS Dashboard demonstration unit.';
    $data->summaryformat = FORMAT_HTML;
    $data->visible = 1;
    $data->startdate = make_timestamp(2025, 3, 1);
    $course = create_course($data);
    echo "Created course id={$course->id}\n";
} else {
    echo "Course exists id={$course->id}\n";
}

// ---- Teacher (Unit Coordinator) ----
$teacher = ensure_user('pcole', 'Peter', 'Cole', 'p.cole@murdoch.edu.au', 'Teach#2026pw');
enrol_user_in($course->id, $teacher->id, 'editingteacher');
echo "Teacher pcole id={$teacher->id}\n";

// ---- Students (live demo accounts; gender encoded by first name John=male, Joy=female) ----
// 14 John (male) + 6 Joy (female) = 20 demo students, mirroring the real cohort ratio.
$students = [];
for ($i=1; $i<=20; $i++) {
    $gender = ($i <= 14) ? 'John' : 'Joy';
    $num = str_pad($i, 3, '0', STR_PAD_LEFT);
    $username = 'student'.$num;
    $u = ensure_user($username, $gender, 'Surname'.$num, $username.'@example.com', 'Stud#2026pw');
    enrol_user_in($course->id, $u->id, 'student');
    $students[] = $u;
}
echo "Enrolled ".count($students)." students\n";

// ---- Activities across 6 weekly sections ----
$existing = $DB->count_records('course_modules', ['course'=>$course->id]);
$pagedefaults = ['display'=>5, 'printheading'=>1, 'printintro'=>0, 'printlastmodified'=>1];
$urldefaults  = ['display'=>0, 'printintro'=>1, 'parameters'=>'', 'externalref'=>''];
$forumdefaults = ['type'=>'general','forcesubscribe'=>0,'trackingtype'=>1,'maxbytes'=>0,
    'maxattachments'=>1,'displaywordcount'=>0,'lockdiscussionafter'=>0,'blockafter'=>0,
    'blockperiod'=>0,'warnafter'=>0,'assessed'=>0,'scale'=>0,'grade_forum'=>0,
    'duedate'=>0,'cutoffdate'=>0];
$assigndefaults = ['alwaysshowdescription'=>1,'submissiondrafts'=>0,'requiresubmissionstatement'=>0,
    'sendnotifications'=>0,'sendlatenotifications'=>0,'sendstudentnotifications'=>1,
    'duedate'=>0,'cutoffdate'=>0,'gradingduedate'=>0,'allowsubmissionsfromdate'=>0,
    'grade'=>100,'teamsubmission'=>0,'requireallteammemberssubmit'=>0,'teamsubmissiongroupingid'=>0,
    'blindmarking'=>0,'hidegrader'=>0,'revealidentities'=>0,'attemptreopenmethod'=>'none',
    'maxattempts'=>-1,'markingworkflow'=>0,'markingallocation'=>0,'activity'=>'',
    'activityformat'=>FORMAT_HTML,'timelimit'=>0,'submissionattachments'=>0,'markinganonymous'=>0,
    'assignsubmission_onlinetext_enabled'=>1,'assignsubmission_file_enabled'=>0,
    'assignsubmission_comments_enabled'=>0,'assignfeedback_comments_enabled'=>1,
    'assignfeedback_comments_commentinline'=>0,'assignfeedback_file_enabled'=>0,
    'assignfeedback_editpdf_enabled'=>0];

if ($existing < 2) {
    $made = 0;
    for ($w=1; $w<=6; $w++) {
        try {
            add_activity($course, 'page', $w, "Week $w: Lecture notes", "<p>Lecture material for week $w.</p>",
                array_merge($pagedefaults, ['content'=>"<h3>Week $w content</h3><p>Read the notes and complete the lab.</p>", 'contentformat'=>FORMAT_HTML]));
            $made++;
            add_activity($course, 'url', $w, "Week $w: Lab description", "Lab handout for week $w",
                array_merge($urldefaults, ['externalurl'=>'https://docs.moodle.org/']));
            $made++;
            add_activity($course, 'forum', $w, "Week $w: Discussion", "Ask questions about week $w", $forumdefaults);
            $made++;
        } catch (Exception $e) { echo "WARN week $w: ".$e->getMessage()."\n"; }
    }
    try {
        add_activity($course, 'assign', 0, 'Assignment 1', '<p>First assignment (weight 10%).</p>',
            array_merge($assigndefaults, ['duedate'=>make_timestamp(2025,4,15)])); $made++;
        add_activity($course, 'assign', 0, 'Assignment 2', '<p>Second assignment (weight 10%).</p>',
            array_merge($assigndefaults, ['duedate'=>make_timestamp(2025,5,20)])); $made++;
    } catch (Exception $e) { echo "WARN assign: ".$e->getMessage()."\n"; }
    rebuild_course_cache($course->id, true);
    echo "Activities created: $made\n";
} else {
    echo "Activities already present ($existing modules)\n";
}

echo "SETUP_DONE course_url={$CFG->wwwroot}/course/view.php?id={$course->id}\n";
