"""
AutoDesk - Synthetic IT support ticket dataset generator
========================================================

Creates ``ml/dataset/tickets.csv`` with 1,500 labelled examples across the six
SRS categories. Every row has the columns required by the SRS::

    text, category, priority

Diversity strategy
------------------
Each category owns three pools:

* ``SUBJECTS``  - the opening line, i.e. what the employee noticed.
* ``DETAILS``   - the body, i.e. what actually happens.
* ``CONTEXTS``  - situational modifiers ("it started this morning").

A row is ``SUBJECT + DETAIL [+ CONTEXT]``. Because the pools are large and the
final text is de-duplicated, the generated corpus contains 1,500 *distinct*
tickets rather than 1,500 variations of one sentence.

``priority`` is produced by the real backend priority engine
(``backend/app/services/priority_engine.py``) so the dataset labels can never
drift away from what the running system assigns.

Usage::

    python ml/generate_data.py                 # writes tickets.csv (default 1500)
    python ml/generate_data.py --rows 3000 --seed 42
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from typing import Dict, List, Tuple

# Make the backend services importable so labels match production behaviour.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.priority_engine import predict_priority  # noqa: E402

DEFAULT_ROWS = 1500
DATASET_DIR = os.path.join(_HERE, "dataset")
TICKETS_CSV = os.path.join(DATASET_DIR, "tickets.csv")


# ===========================================================================
# Content pools
# ===========================================================================
SUBJECTS: Dict[str, List[str]] = {
    "Software": [
        "Microsoft Word crashes every time I open it",
        "Excel spreadsheet will not open from the shared drive",
        "Outlook keeps asking for my password again and again",
        "The Teams application will not start on my laptop",
        "Adobe Acrobat shows an error when opening a PDF",
        "AutoCAD crashes while I am working on a drawing",
        "Python script fails with a module not found error",
        "Visual Studio Code cannot find my project folder",
        "Google Chrome is extremely slow and keeps hanging",
        "Zoom application freezes during screen sharing",
        "PowerPoint freezes when I play a slide transition",
        "The company antivirus software blocks a legitimate application",
        "Slack notifications stopped arriving on my desktop",
        "Notion desktop application does not sync my changes",
        "The PDF reader keeps opening in the wrong application",
        "MATLAB licence expired and blocks my project",
        "Windows Update breaks an application I use daily",
        "My macro in Excel stopped working after the update",
        "OneNote will not sync my notebooks to the company account",
        "The browser cannot play embedded videos on the intranet",
        "Sublime Text shows an encoding error in every file",
        "The printer queue software keeps rejecting my documents",
        "Autodesk Revit crashes when I open a shared project",
        "My database client cannot connect to the reporting server",
        "The image editor refuses to save in the required format",
        "An update broke the video calling feature in my browser",
        "Windows Defender keeps quarantining a file I need",
        "The internal reporting portal shows a server error",
        "My keyboard shortcut layout stopped working in the editor",
        "A required software licence key is rejected at startup",
    ],
    "Hardware": [
        "My keyboard is not responding",
        "The monitor flickers and goes black for a few seconds",
        "My laptop fan makes a very loud noise",
        "The USB port on my laptop stopped recognising devices",
        "My mouse pointer jumps around the screen randomly",
        "The office printer prints blank pages",
        "My laptop battery drains very quickly",
        "The external hard disk is not detected by my laptop",
        "My headset microphone is not picking up my voice",
        "The docking station does not connect to any display",
        "My laptop screen has a strange blue tint",
        "The webcam on my laptop shows a black screen",
        "My desktop restarts itself randomly",
        "The touchpad on my laptop has stopped responding",
        "My USB headset disconnects every few minutes",
        "The office scanner cannot read documents",
        "My laptop will not charge even with the original charger",
        "The speakers in my monitor produce no sound at all",
        "My SSD drive is failing and the machine is very slow",
        "The power adapter on my laptop gets very hot",
        "My second monitor is detected but shows no signal",
        "The ethernet cable port on my laptop is physically damaged",
        "My laptop keyboard has several dead keys",
        "The barcode scanner at my desk does not read any barcode",
        "My computer makes a clicking noise from the hard disk",
        "The graphics card fan stops and the machine overheats",
        "My laptop screen has a crack and flickers when opened",
        "The front panel USB ports on my desktop do nothing",
        "My wired network card is not detected in the system",
        "The fingerprint reader on my laptop never responds",
    ],
    "Network": [
        "My laptop cannot connect to the office WiFi",
        "The internet connection at my desk keeps dropping",
        "I cannot reach any website from my office desktop",
        "The office WiFi is extremely slow today",
        "My computer shows a network cable unplugged error",
        "The internal shared drive is not reachable from my machine",
        "I cannot ping the internal file server from my laptop",
        "The intranet portal will not load in my browser",
        "WiFi disconnects from my laptop every few minutes",
        "The network drive in Windows keeps showing as unavailable",
        "My ethernet connection says media disconnected",
        "Other colleagues in my department cannot connect either",
        "DNS resolution fails for every company website",
        "The guest WiFi password does not work for my device",
        "I get no internet access even though WiFi is connected",
        "The office wireless network does not show my laptop at all",
        "Network shares on the file server time out constantly",
        "My laptop connects to WiFi but has no internet",
        "The bandwidth in the meeting room is unusable for video calls",
        "The proxy settings block every external website",
        "My laptop cannot see the shared printer on the network",
        "The whole office network is down this morning",
        "Packet loss to the data centre is making my work impossible",
        "The switch port at my desk does not light up at all",
        "I cannot access the internet from the second floor",
        "My desktop has no network adapter listed in the system",
        "The DNS server address may be incorrect on my machine",
        "Network drive disconnects every time I reboot my laptop",
        "The internal network is extremely congested during peak hours",
        "My laptop shows limited network connectivity with an X mark",
    ],
    "Login": [
        "I forgot my company password",
        "My password stopped working this morning",
        "My account gets locked after three login attempts",
        "I cannot log in to my email account",
        "The password reset email never arrives",
        "My account says it is locked and I cannot unlock it",
        "I changed my password and now nothing works",
        "My login keeps looping back to the sign-in screen",
        "The system says my credentials are invalid every time",
        "I am asked to change my password but the new one is rejected",
        "My multi factor authentication code is never accepted",
        "I cannot sign in to my laptop after the weekend",
        "My username is no longer recognised by the login page",
        "The login page keeps spinning and never finishes",
        "I am locked out of my account after too many attempts",
        "The password reset link always says it has expired",
        "My account is suspended and I do not know why",
        "I cannot authenticate to the internal reporting system",
        "My single sign on keeps bouncing between the identity page",
        "The temporary password given to me does not work",
        "I get a permissions error when signing in to the portal",
        "My login credentials work on the desktop but not on the laptop",
        "The system tells me my account has expired",
        "I cannot enter the correct password even with caps lock off",
        "My previous password is still cached somewhere in the browser",
        "The two factor authentication app shows an invalid code",
        "I am unable to sign in after the password policy change",
        "The domain login rejects my account every single time",
        "My account asks for a password change on every single login",
        "The PIN for my domain account is rejected at the sign-in prompt",
    ],
    "VPN": [
        "VPN keeps disconnecting when I connect remotely",
        "I cannot connect to the company VPN from home",
        "The VPN client fails with an authentication error",
        "My VPN connects but I cannot reach any internal website",
        "The VPN tunnel drops every fifteen minutes",
        "The VPN client says the connection was refused",
        "I get error 809 when connecting to the VPN",
        "The VPN works on the office network but not from home",
        "My VPN disconnects whenever I switch wifi networks",
        "The VPN software is stuck on the connecting screen",
        "I am unable to establish a VPN tunnel from my laptop",
        "The VPN certificate expired and the client will not connect",
        "My VPN connects without internet access at all",
        "The VPN client crashes immediately after I start it",
        "I cannot download the VPN profile onto my new phone",
        "The VPN shows connected but no company drive is available",
        "My VPN disconnects every time I answer a call",
        "The VPN login window does not accept my password",
        "The VPN cannot resolve internal hostnames once connected",
        "The VPN client is not accepting my OTP code",
        "I get disconnected from VPN when using the printer remotely",
        "The VPN profile on my laptop is missing after the reimage",
        "The VPN connection is extremely slow during peak hours",
        "My VPN will not start because of a driver error",
        "The VPN drops whenever I connect to a conference call",
        "I cannot reach the shared drive through the VPN tunnel",
        "The VPN client reports an invalid gateway address",
        "My home router blocks the VPN port and I cannot connect",
        "The VPN keeps asking me to accept a certificate warning",
        "The VPN session ends instantly on the mobile network",
    ],
    "Access": [
        "I need permission to access the HR portal",
        "I cannot access the shared marketing folder",
        "The finance system says I do not have permission",
        "I need read access to the analytics dashboard",
        "My account cannot open the project management tool",
        "I am not able to access the design repository",
        "I need access to the production database for my project",
        "The document I need returns an access denied error",
        "I need approval to access the confidential archive",
        "I lost access to my project folder after the team move",
        "The new starter portal rejects my employee ID",
        "I need write access to the shared documentation",
        "My request for the finance folder was never approved",
        "I cannot open the restricted customer data folder",
        "I need access to the build server for my internship task",
        "The admin console denies access even for my own profile",
        "I need permission to install software on my laptop",
        "I cannot access the printer queue folder from my laptop",
        "My group membership is missing so I see access denied",
        "I need access to the training platform before the new course",
        "The shared calendar is not visible to me at all",
        "I need to be added to the on call rotation list",
        "I cannot download files from the partner portal",
        "My access to the version control repository was revoked",
        "I need permission to view the quarterly financial reports",
        "The wiki page returns forbidden for my user account",
        "I need to be granted access to the lab booking system",
        "I cannot approve purchase requests in the procurement tool",
        "I need admin rights on the reporting server for migration work",
        "The file I own transferred to another department and I lost access",
    ],
}

DETAILS: Dict[str, List[str]] = {
    "Software": [
        "It started after the update that was installed on Tuesday.",
        "The rest of the machine works fine and the internet is normal.",
        "I have already tried restarting the application and the laptop.",
        "The same file opens correctly on my colleague's machine.",
        "An error dialog appears and then the program closes by itself.",
        "This happens with every document I try to open.",
        "Nothing changed on my side and I have not installed anything new.",
        "The application works fine when I am not connected to the office network.",
        "It is very slow to load and eventually gives up with an error.",
        "Windows event viewer shows an application fault for the same program.",
        "The problem started this morning without any change from my end.",
        "Reinstalling the application did not resolve the issue.",
        "Only my account is affected, the other user on the same machine is fine.",
        "The application keeps popping up a license activation dialog.",
        "I get a stack trace instead of the normal output window.",
        "The feature worked last week and simply stopped working since.",
        "Antivirus is not flagging anything but the program still refuses to run.",
        "The error appears consistently and there is no way to bypass it.",
        "I have the latest version installed and the problem is still there.",
        "It affects my daily work so I would like this looked at quickly.",
        "Running the program as administrator does not help at all.",
        "The problem appears both on my laptop and on the office desktop.",
        "Every time I close the program it asks me to send a crash report.",
        "The file I am working on is stored on the network share.",
        "The application hangs and I have to force quit it several times a day.",
        "I have cleared the cache and reinstalled the runtime dependencies.",
        "There is a yellow warning triangle in the corner of the window.",
        "The program opens in compatibility mode instead of the normal mode.",
        "It started failing right after the quarterly software rollout.",
        "The same application works fine on my personal laptop.",
    ],
    "Hardware": [
        "The problem started this morning and it happens every single time.",
        "I have reseated the cable and tried a different port on the machine.",
        "My colleague with the same model of machine has no problem at all.",
        "The device is only two years old and was working fine until now.",
        "Windows device manager reports an error code for the hardware.",
        "The machine still works but this one part of the setup is unusable.",
        "It happens regardless of which application I am working in.",
        "I already tried on a different cable and a different port.",
        "The device manager shows a warning that the device cannot start.",
        "This is making the whole desk unusable for me during the working day.",
        "The problem appears intermittently and then becomes permanent.",
        "It survived a restart and a complete shutdown of the machine.",
        "There is a physical crack or mark on the part that I can see.",
        "The device works on a different computer so the fault is with the device.",
        "I hear a clicking or grinding noise coming from the machine.",
        "The machine is overheating and the thermal fan runs constantly.",
        "I dropped the device yesterday and it has not worked since.",
        "Even the technician at the local store could not fix it.",
        "The port feels loose and the cable has to be held at an angle.",
        "Everything on screen works but no sound comes out of the speakers.",
        "It affects the battery life significantly during a normal day of work.",
        "The screen works when docked but not on the laptop panel.",
        "The device shows up in the system but no data is ever transferred.",
        "The machine reports a disk error and it is very slow to boot.",
        "I have tried the device on two different machines with no luck.",
        "The problem started right after the machine was moved to my desk.",
        "The laptop chassis is warm near the charger port.",
        "The manufacturer diagnostic tool reports a hardware failure.",
        "It happens only when the machine is on battery power.",
        "The hardware fault appears as soon as I plug in the external device.",
    ],
    "Network": [
        "The problem started this morning and affects my whole desk.",
        "Other people in the same area are complaining about the same thing.",
        "Restarting the laptop and the network port did not help.",
        "The cable is seated properly and the port light is lit.",
        "It worked fine yesterday and nothing was changed on my machine.",
        "I can see the wireless network but it refuses to connect.",
        "The issue seems to come and go throughout the day.",
        "My phone connects to the same WiFi without any problem.",
        "The support page mentions an ongoing issue in this building.",
        "The internet works in the meeting room but not at my desk.",
        "I can reach the internal systems but no external website loads.",
        "It affects several of us on the same floor since this morning.",
        "I tried the network troubleshooter and it did not resolve anything.",
        "The connection drops roughly every ten minutes without warning.",
        "Nothing on my machine has changed and I have not installed anything.",
        "The wifi signal strength is shown as very weak at my location.",
        "It happens with both the wired and the wireless connection.",
        "The browser shows a DNS probe finished error for every site.",
        "My colleague on the same switch port has exactly the same problem.",
        "The whole floor lost network connectivity for a few minutes.",
        "I can ping my own machine but not any other device on the network.",
        "The problem started after the office network maintenance window.",
        "Even the network printer is unreachable from my machine.",
        "The access point near my desk seems to be offline.",
        "I have tried connecting from home and it works perfectly there.",
        "The network adapter in the system shows a media disconnected state.",
        "It only happens when I am on the office wireless network.",
        "My throughput has dropped to almost nothing during the day.",
        "The proxy is configured automatically and blocks external traffic.",
        "I cannot browse any website even though ping works fine.",
    ],
    "Login": [
        "I am on site and cannot do any of my normal work.",
        "I have tried three different browsers and the same thing happens.",
        "The password reset link in the email says it has already expired.",
        "The account works on the phone but not on the computer.",
        "Someone may have tried to log in to my account many times.",
        "It has worked every day until this morning with no changes.",
        "The login page loads but signing in immediately returns me back.",
        "I have cleared the cookies and tried an incognito window.",
        "The message says the account is temporarily locked out.",
        "I never received any email asking me to change my password.",
        "The password hint on the login page does not match my password.",
        "My colleague can log in fine with their own account on the same machine.",
        "The sign-in works on the office desktop but not on my laptop.",
        "I have retyped the password many times and it is definitely correct.",
        "The two factor code is rejected even when I enter it immediately.",
        "I have been locked out since yesterday evening.",
        "The system says my credentials are invalid for both domains.",
        "The password policy requires a character I cannot type on this keyboard.",
        "My account was working until the maintenance window finished.",
        "I get redirected back to the login page in an endless loop.",
        "The mobile authenticator app does not show any code for me.",
        "My account shows as suspended and support has not responded yet.",
        "I am unable to use any of the internal systems because of this.",
        "The sign-in prompt on my Windows machine rejects the domain account.",
        "The password field resets itself before I finish typing.",
        "It looks like my username has an extra character in it somewhere.",
        "I changed my password last week and it may not have saved.",
        "Every internal application gives me the same authentication error.",
        "The login screen shows an error the moment I press enter.",
        "I need this resolved before the start of the working day.",
    ],
    "VPN": [
        "I am working from home today and need the internal systems.",
        "The client worked on the office wifi but fails on my home connection.",
        "I have tried disconnecting and reconnecting several times.",
        "It worked fine until yesterday and nothing was changed on my machine.",
        "The error message says the gateway is unreachable.",
        "The VPN icon stays on connecting and never completes.",
        "I get the same problem on my phone with the mobile application.",
        "My internet connection at home is stable and fast.",
        "The company resource I need is only available through the VPN.",
        "Reinstalling the VPN profile did not fix the problem.",
        "The client disconnects after roughly fifteen minutes of use.",
        "The connection is accepted but no internal host answers.",
        "I need to reach the payroll system today to finish a task.",
        "The VPN server may be refusing the connection because of my account.",
        "I am behind a home router that may be filtering the traffic.",
        "The client reports an invalid certificate for the gateway.",
        "It disconnects every time I switch between wifi and mobile data.",
        "The same profile works on my personal laptop from home.",
        "I can connect but every internal website times out.",
        "The client gives an authentication failure with my normal password.",
        "I changed my password yesterday and the VPN may not know yet.",
        "The connection drops whenever I run a long download.",
        "My laptop was reimaged and the VPN profile was never restored.",
        "The client is stuck and I have to kill the process each time.",
        "It started failing right after the weekend maintenance.",
        "I cannot reach the internal file share through the tunnel.",
        "The client will not accept the certificate warning prompt.",
        "The mobile network gives a different error than home wifi does.",
        "I need the VPN working for a client call this afternoon.",
        "The tunnel connects but all traffic bypasses the tunnel.",
    ],
    "Access": [
        "I was moved to this team last week and still have no permissions.",
        "My manager has approved the request but it has not taken effect.",
        "The error message clearly says that I do not have permission.",
        "Everyone else on the team can open the resource without any problem.",
        "I need this access to complete my assigned work this week.",
        "The folder is visible in the listing but opening it returns forbidden.",
        "My previous department owned the file and transferred it to mine.",
        "This is required for the project I have been assigned to.",
        "The permission request form does not list the resource I need.",
        "I can see the folder name but the contents are not accessible.",
        "The access rights I had were lost after the account migration.",
        "The new starter process should have granted me this automatically.",
        "My user account is not a member of the correct security group.",
        "I only need read access, not full editing rights.",
        "The system administrator granted it directly in the database.",
        "It is a confidential folder so the access has to be approved first.",
        "I need to complete an audit that requires these documents.",
        "The portal returns an unauthorized error for every page I open.",
        "My role in the organisation changed and permissions were not updated.",
        "The access was granted in the previous project space only.",
        "I have read access but cannot download or export the files.",
        "The request has been sitting in the approval queue for days.",
        "I need to approve items myself as part of my new responsibilities.",
        "The resource is shared with me but the permissions are read only.",
        "The application hides the menu option because of my current role.",
        "I need this before the new system goes live next month.",
        "The permission was removed when the project was archived.",
        "I cannot assign tasks in the tool because of my role.",
        "The training platform will not let me enrol in the course.",
        "Access was granted to the wrong user id for my account.",
    ],
}

CONTEXTS: List[str] = [
    "",
    "",
    "",
    "Please let me know if you need any further information from my side.",
    "Let me know if you need me to try anything else.",
    "I am happy to try any steps you suggest.",
    "This is affecting my daily work so a quick response would help.",
    "I have attached a screenshot of the error message.",
    "Let me know the earliest time you can look at this.",
    "I tried the obvious steps from the knowledge base first.",
    "This started during the morning and has not improved since.",
    "I am currently working remotely so this blocks my day.",
    "I am in the office today and can be at my desk if needed.",
    "My manager is copied on this request for visibility.",
    "I have already checked with my colleagues and they are fine.",
    "Please treat this as time sensitive for my team.",
    "I have written down everything exactly as it appears on screen.",
    "The IT self service portal did not help with this issue.",
    "I would appreciate an update once this is resolved.",
    "Please advise on the next step I should take.",
    "I can provide remote access if the technician needs it.",
    "Nothing was installed or changed by me before this happened.",
    "The problem is reproducible every single time I try.",
    "I have included the exact error text for reference.",
    "This has been happening intermittently over the last week.",
    "I need this working before my next client meeting.",
    "Kindly look at this at the earliest convenience.",
    "I have tried both on the laptop and on the office desktop.",
    "My request number from the portal is referenced below.",
    "The behaviour looks identical to a known issue in the release notes.",
    "I am happy to escalate this further if that helps.",
    "Please resolve this as soon as possible as I am blocked.",
    # --- escalation scenarios: keep these few so the priority distribution in
    # --- the dataset stays realistic instead of being dominated by Medium/Low.
    "This is a complete outage and the entire floor has stopped working.",
    "This is urgent, I cannot work and the department is unavailable.",
    "Several of us in the team are affected by the same major issue.",
    "",
    "",
    "",
    "",
]


def _sentence_case(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    return text[0].upper() + text[1:]


def _assemble(rng: random.Random, category: str) -> str:
    """Build one distinct ticket body for *category*."""
    subject = rng.choice(SUBJECTS[category])
    detail = rng.choice(DETAILS[category])
    context = rng.choice(CONTEXTS)
    parts = [_sentence_case(subject).rstrip("."), detail]
    if context:
        parts.append(context)
    return ". ".join(parts) + "."


def generate_dataset(rows: int = DEFAULT_ROWS, seed: int = 2025) -> List[Dict[str, str]]:
    """
    Generate exactly *rows* unique labelled tickets, evenly split across the
    six SRS categories.
    """
    rng = random.Random(seed)
    categories = list(SUBJECTS.keys())
    if len(categories) != 6:
        raise RuntimeError(f"expected 6 categories, found {len(categories)}")

    per_category, remainder = divmod(rows, len(categories))
    quotas = [per_category + (1 if i < remainder else 0) for i in range(len(categories))]

    records: List[Dict[str, str]] = []
    seen: set[str] = set()

    for category, quota in zip(categories, quotas):
        produced = 0
        attempts = 0
        # Cap attempts so an impossible quota fails loudly instead of hanging.
        while produced < quota and attempts < quota * 400:
            attempts += 1
            text = _assemble(rng, category)
            key = " ".join(text.lower().split())
            if key in seen:
                continue
            seen.add(key)
            priority_result = predict_priority(description=text)
            records.append(
                {
                    "text": text,
                    "category": category,
                    "priority": priority_result["priority"],
                }
            )
            produced += 1
        if produced < quota:
            raise RuntimeError(
                f"could only generate {produced}/{quota} unique '{category}' tickets; "
                "increase the content pools"
            )

    rng.shuffle(records)
    return records


def write_dataset(records: List[Dict[str, str]], path: str = TICKETS_CSV) -> str:
    """Write *records* to *path* as CSV with a header row."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text", "category", "priority"])
        writer.writeheader()
        writer.writerows(records)
    return path


def summarize(records: List[Dict[str, str]]) -> str:
    """Return a small console summary of the generated dataset."""
    by_category: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}
    for row in records:
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1
        by_priority[row["priority"]] = by_priority.get(row["priority"], 0) + 1

    lengths = [len(r["text"].split()) for r in records]
    lines = [
        "",
        "AutoDesk dataset generated",
        "=" * 60,
        f"Total rows        : {len(records)}",
        f"Unique texts      : {len({r['text'].lower() for r in records})}",
        f"Word length       : min={min(lengths)} max={max(lengths)} "
        f"avg={sum(lengths) / len(lengths):.1f}",
        "",
        "By category:",
    ]
    for category in SUBJECTS:
        lines.append(f"  {category:<10} {by_category.get(category, 0):>5}")
    lines += ["", "By priority:"]
    for priority in ("Critical", "High", "Medium", "Low"):
        lines.append(f"  {priority:<10} {by_priority.get(priority, 0):>5}")
    lines += ["=" * 60, ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the AutoDesk ticket dataset")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--seed", type=int, default=2025)
    parser.add_argument("--out", default=TICKETS_CSV)
    args = parser.parse_args()

    records = generate_dataset(args.rows, args.seed)
    path = write_dataset(records, args.out)
    print(summarize(records))
    print(f"Written to: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
