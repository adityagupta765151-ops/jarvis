"""What the model is allowed to do, and how it is described to it.

Every tool module stays unaware of the model: it just exposes functions.
This file is the only place that knows about schemas, and the only place
that has to change when a tool is added.
"""
from __future__ import annotations

from ..app import stats
from ..app.config import log
from ..jobs import apply as job_apply
from ..jobs import dashboard as job_dashboard
from ..jobs import engine as job_engine
from ..jobs import resume as job_resume
from ..store import memory
from ..voice import speaking
from . import apps, browser, contacts, files, reminders, screen, system, whatsapp, whatsapp_web
from .permissions import NEEDS_CONFIRMATION  # re-exported; see __init__

FUNCTIONS = {
    # files
    "list_dir": files.list_dir,
    "read_file": files.read_file,
    "write_file": files.write_file,
    "edit_file": files.edit_file,
    "create_folder": files.create_folder,
    "move_path": files.move_path,
    "copy_path": files.copy_path,
    "delete_path": files.delete_path,
    "search_files": files.search_files,
    # system
    "run_command": system.run_command,
    "open_in_vscode": system.open_in_vscode,
    "open_url": system.open_url,
    "search_web": system.search_web,
    "get_datetime": system.get_datetime,
    "get_system_info": system.get_system_info,
    # applications
    "open_app": apps.open_app,
    "close_app": apps.close_app,
    # browser
    "open_page": browser.open_page,
    "read_page": browser.read_page,
    "summarize_page": browser.summarize_page,
    "search_web_and_read": browser.search_web_and_read,
    "find_on_page": browser.find_on_page,
    "click_text": browser.click_text,
    "fill_field": browser.fill_field,
    "press_key": browser.press_key,
    "browser_screenshot": browser.browser_screenshot,
    "close_browser": browser.close_browser,
    # whatsapp, desktop app and browser
    "open_whatsapp": whatsapp.open_whatsapp,
    "open_contact": whatsapp.open_contact,
    "draft_whatsapp_message": whatsapp.draft_whatsapp_message,
    "send_whatsapp_message": whatsapp.send_whatsapp_message,
    "add_contact": whatsapp.add_contact,
    "wa_open": whatsapp_web.wa_open,
    "wa_contacts": whatsapp_web.wa_contacts,
    "wa_open_chat": whatsapp_web.wa_open_chat,
    "wa_draft_web": whatsapp_web.wa_draft_web,
    "wa_send_web": whatsapp_web.wa_send_web,
    "wa_read_chat": whatsapp_web.wa_read_chat,
    # contacts
    "import_contacts": contacts.import_contacts,
    "find_contacts": contacts.find_contacts,
    "count_contacts": contacts.count_contacts,
    # reminders
    "set_reminder": reminders.set_reminder,
    "list_reminders": reminders.list_reminders,
    "cancel_reminders": reminders.cancel_reminders,
    # memory
    "remember": memory.remember,
    "forget": memory.forget,
    "recall": memory.recall,
    # screen
    "take_screenshot": screen.take_screenshot,
    "describe_screen": screen.describe_screen,
    # voice
    "voice_report": speaking.voice_report,
    # job hunting
    "scan_resume": job_resume.scan_resume,
    "show_resume_profile": job_resume.show_profile,
    "set_job_preference": job_resume.set_preference,
    "find_jobs": job_engine.find_jobs,
    "top_matches": job_engine.top_matches,
    "why_this_job": job_engine.why_this_job,
    "missing_skills": job_engine.missing_skills,
    "shortlist_job": job_engine.shortlist,
    "open_job_board": job_engine.open_board,
    "application_status": job_engine.application_status,
    "effectiveness": job_engine.effectiveness,
    "prepare_application": job_apply.prepare_application,
    "mark_applied": job_apply.mark_applied,
    "mark_job_status": job_apply.mark_status,
    "open_job_dashboard": job_dashboard.open_dashboard,
}


def execute_tool(name: str, args: dict) -> str:
    """Run a tool and always come back with a sentence, never an exception.

    The model reads the result, so an error has to be describable rather
    than fatal.
    """
    fn = FUNCTIONS.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    stats.tool_started(name)
    try:
        return fn(**args)
    except TypeError as e:
        return f"Wrong arguments for {name}: {e}"
    except Exception as e:  # noqa: BLE001
        log(f"{name} failed: {e}")
        return f"Error in {name}: {type(e).__name__}: {e}"
    finally:
        stats.tool_finished(name)


def _schema(name, description, props=None, required=None):
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props or {},
                             "required": required or []}}


S, I = {"type": "string"}, {"type": "integer"}

TOOL_SCHEMAS = [
    _schema("list_dir", "Show the folder tree inside the workspace.", {"path": S, "depth": I}),
    _schema("read_file", "Read a text file, PDF or Word document.",
            {"path": S, "start_line": I, "end_line": I}, ["path"]),
    _schema("write_file", "Create or overwrite a file. Existing files are backed up first.",
            {"path": S, "content": S}, ["path", "content"]),
    _schema("edit_file", "Replace one exact, unique block of text in a file.",
            {"path": S, "old_text": S, "new_text": S}, ["path", "old_text", "new_text"]),
    _schema("create_folder", "Create a folder.", {"path": S}, ["path"]),
    _schema("move_path", "Move or rename a file or folder.",
            {"source": S, "destination": S}, ["source", "destination"]),
    _schema("copy_path", "Copy a file or folder.",
            {"source": S, "destination": S}, ["source", "destination"]),
    _schema("delete_path", "Delete a file or folder. The user confirms first.",
            {"path": S}, ["path"]),
    _schema("search_files", "Find files by glob like '*.py', optionally by text inside them.",
            {"name_pattern": S, "contains": S, "path": S}),
    _schema("run_command", "Run a shell command. The user confirms first.",
            {"command": S, "cwd": S}, ["command"]),
    _schema("open_in_vscode", "Open a file or folder in VS Code, optionally at a line.",
            {"path": S, "line": I}),
    _schema("open_url", "Just open a website in the user's normal browser. You cannot read "
                        "the page afterwards, so prefer read_page when the content matters.",
            {"url": S}, ["url"]),
    _schema("search_web", "Open a Google search in the user's normal browser, results unread.",
            {"query": S}, ["query"]),
    _schema("get_datetime", "Current local date and time."),
    _schema("get_system_info", "OS, Python version and workspace path."),
    _schema("open_app", "Open a desktop app by name: chrome, vs code, whatsapp, spotify, "
                        "calculator.", {"name": S}, ["name"]),
    _schema("close_app", "Close a running desktop app by name.", {"name": S}, ["name"]),
    _schema("open_page", "Open a page in JARVIS's own browser, which you can then read and click.",
            {"url": S}, ["url"]),
    _schema("read_page", "Read the visible text of a web page. Pass a url, or omit it to read "
                         "the page already open.", {"url": S}),
    _schema("summarize_page", "Read a page and summarise it, or answer a question about it.",
            {"url": S, "question": S}),
    _schema("search_web_and_read", "Search the web and return the top results with their links, "
                                   "so you can actually use them.",
            {"query": S, "count": I}, ["query"]),
    _schema("find_on_page", "Ask something about the open page: a price, a date, a heading.",
            {"what": S}, ["what"]),
    _schema("click_text", "Click a link or button by the words on it. The user confirms if it "
                          "looks like it buys, sends, submits or deletes something.",
            {"text": S}, ["text"]),
    _schema("fill_field", "Type into a form field, found by its label or placeholder.",
            {"label": S, "value": S}, ["label", "value"]),
    _schema("press_key", "Press a key on the page, usually Enter to submit a search box.",
            {"key": S}),
    _schema("browser_screenshot", "Save a picture of the page JARVIS's browser is showing."),
    _schema("close_browser", "Close JARVIS's browser and free its memory."),
    _schema("open_whatsapp", "Open WhatsApp."),
    _schema("open_contact", "Open a WhatsApp chat with a saved contact.", {"name": S}, ["name"]),
    _schema("draft_whatsapp_message",
            "Open a chat with a message typed in but NOT sent. Use this for any new message.",
            {"name": S, "message": S}, ["name", "message"]),
    _schema("send_whatsapp_message",
            "Send the drafted WhatsApp message. The user confirms first.",
            {"name": S, "message": S}),
    _schema("add_contact", "Save a contact name and phone number with country code.",
            {"name": S, "number": S}, ["name", "number"]),
    _schema("wa_open", "Open WhatsApp Web in JARVIS's browser. Needs a one-time QR scan."),
    _schema("wa_contacts", "List the people in the WhatsApp chat list. Use this when the user "
                           "asks who they can message.", {"limit": I}),
    _schema("wa_open_chat", "Open someone's WhatsApp chat by searching their name in WhatsApp "
                            "Web. Works for any name in the chat list, no saved number needed.",
            {"name": S}, ["name"]),
    _schema("wa_draft_web", "Type a WhatsApp message to someone in the browser without sending "
                            "it. Prefer this over draft_whatsapp_message when the person isn't "
                            "in saved contacts.", {"name": S, "message": S}, ["name", "message"]),
    _schema("wa_send_web", "Send the message typed in WhatsApp Web. The user confirms first.",
            {"name": S, "message": S}),
    _schema("wa_read_chat", "Read the last few messages in the open WhatsApp chat.", {"count": I}),
    _schema("import_contacts", "Import many contacts at once from a Google Contacts CSV "
                               "export or a .vcf vCard file.",
            {"path": S, "country_code": S}, ["path"]),
    _schema("find_contacts", "Search saved contacts by part of a name.", {"query": S}, ["query"]),
    _schema("count_contacts", "How many contacts are saved."),
    _schema("set_reminder", "Remind the user later. when can be '8 pm' or 'in 10 minutes'.",
            {"text": S, "when": S}, ["text", "when"]),
    _schema("list_reminders", "List pending reminders."),
    _schema("cancel_reminders", "Cancel all pending reminders."),
    _schema("remember", "Store a preference the user tells you to remember.",
            {"key": S, "value": S}, ["key", "value"]),
    _schema("forget", "Forget a stored preference.", {"key": S}, ["key"]),
    _schema("recall", "Recall stored preferences.", {"key": S}),
    _schema("take_screenshot", "Save a screenshot of the screen."),
    _schema("describe_screen", "Capture the screen and describe or explain what's on it.",
            {"question": S}),
    _schema("voice_report", "Which speech engine and voice JARVIS is using, and what else "
                            "is available."),
    _schema("scan_resume", "Read a resume (PDF, Word, image or text) and build the "
                           "candidate profile everything else matches against.",
            {"path": S}, ["path"]),
    _schema("show_resume_profile", "Show what JARVIS knows about the candidate."),
    _schema("set_job_preference", "Set roles, locations, countries or work_modes for job "
                                  "search. Value is a comma separated list.",
            {"field": S, "value": S}, ["field", "value"]),
    _schema("find_jobs", "Search the job boards, score every result against the resume "
                         "and store them. Leave query empty to use the saved target role.",
            {"query": S, "location": S, "limit": I}),
    _schema("top_matches", "Show the best stored jobs with their scores and skill gaps.",
            {"count": I, "min_score": I}),
    _schema("why_this_job", "Explain a job's score in full. Reference is a rank number "
                            "or part of the company name.", {"reference": S}, ["reference"]),
    _schema("missing_skills", "Which skills employers keep asking for that the resume "
                              "doesn't list.", {"limit": I}),
    _schema("shortlist_job", "Mark a stored job as one to go for.",
            {"reference": S}, ["reference"]),
    _schema("open_job_board", "Open LinkedIn, Naukri, Indeed, Internshala or Wellfound "
                              "in the browser to search by hand. JARVIS cannot automate "
                              "these; their terms forbid it.",
            {"board": S, "query": S, "location": S}, ["board"]),
    _schema("application_status", "List the applications recorded so far."),
    _schema("effectiveness", "Success rate, interview rate and match averages."),
    _schema("prepare_application", "Open a job posting and fill the fields the resume can "
                                   "answer. Never submits: the user presses submit.",
            {"reference": S}, ["reference"]),
    _schema("mark_applied", "Record that the user submitted an application themselves.",
            {"reference": S, "notes": S}, ["reference"]),
    _schema("mark_job_status", "Set a job's status: shortlisted, applied, interview, "
                               "rejected, offer, withdrawn.",
            {"reference": S, "status": S}, ["reference", "status"]),
    _schema("open_job_dashboard", "Start and open the job dashboard at localhost:3000/jobs."),
]
