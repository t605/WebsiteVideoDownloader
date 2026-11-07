===============================================================
  VIDEO DOWNLOADER                                  version 9.13
  Saves videos from the internet to your computer, in 480p
===============================================================

Works with YouTube, VK, Vimeo, Facebook, Instagram, TikTok,
online course pages and about 1,700 other websites.

The program speaks English or Russian - see "Language" in
section 3.


CONTENTS
--------
  1. What you need
  2. First time setup
  3. Downloading a video
  4. Several videos on one page
  5. Log in to websites (only if a video refuses to download)
  6. If something goes wrong
  7. The self test and "Details for helper"
  8. Things worth knowing
  9. What it cannot do
 10. Files in this package
     Quick reference


---------------------------------------------------------------
  1. WHAT YOU NEED
---------------------------------------------------------------

  * A Windows 10 or 11 computer.
  * An internet connection.
  * About 5 minutes for the first start. Nothing to install by
    hand - the launcher does it all, including Python itself.


---------------------------------------------------------------
  2. FIRST TIME SETUP  (about 5 minutes, done once)
---------------------------------------------------------------

STEP 1 - Unzip the files
------------------------
Unzip WebsiteVideoDownloader.zip into a folder of your own,
for example  Documents\VideoDownloader\ . Do not run it from
inside the zip file.

The folder then holds three files:

    VideoDownloader.bat    <- the one you double-click
    VideoDownloader.py     <- the program itself
    README.txt             <- this file

They must stay together in the SAME folder. If you separate
them, the launcher will say it cannot find the program.


STEP 2 - Double-click VideoDownloader.bat
-----------------------------------------
That is the whole setup.

A black window opens and walks through four checks:

    [1 of 4]  Looking for Python...
    [2 of 4]  Checking the download engine...
    [3 of 4]  Checking secure connections...
    [4 of 4]  Checking the helper module (FFmpeg)...

If Python is missing it will ask:

    Install Python now [Y,N]?

Press  Y  and Enter. It downloads and installs Python by
itself. This takes a few minutes. Do not close the window.

When all four checks pass, the Video Downloader window opens.

The first run takes a few minutes. Every run after that takes
a few seconds.


IF IT ASKS YOU TO RESTART
-------------------------
Occasionally Windows does not notice a brand new Python until
the computer restarts. If you see:

    "Please RESTART THE COMPUTER, then double-click this
     launcher again."

then restart, double-click VideoDownloader.bat again, and it
will continue. This only ever happens once.


STEP 3 - Make a Desktop shortcut  (optional but recommended)
------------------------------------------------------------
So you do not have to open the folder every time.

  1. Right-click  VideoDownloader.bat
  2. Choose "Show more options" if you are on Windows 11
  3. Choose "Send to"  ->  "Desktop (create shortcut)"
  4. A "VideoDownloader" icon appears on your Desktop
  5. Right-click it, choose "Rename", and call it
     "Video Downloader"

From now on, just double-click that.


---------------------------------------------------------------
  3. DOWNLOADING A VIDEO
---------------------------------------------------------------

  1. In your web browser, open the page with the video
  2. Copy the address from the bar at the top of the browser
       (click it, then press CTRL and C together)
  3. Switch to Video Downloader. The address usually appears
     in the box by itself. If it does not, press the blue
     "Paste link" button.
  4. Under the box the program shows what it found, for
     example   Found: Grandchildren's concert
               youtube.com  .  12:30
     so you can check it is the right video.
  5. Press the big green "Download video" button.
     Only want the sound (a lecture, a concert, music)? Above the
     green button, choose "Sound only (MP3)" first. The button then
     says "Download sound" and you get a file ending in .mp3
     (same folder as videos) instead of a video. The sound is
     saved as MP3 at 192 kbit/s, whatever the video quality.
     The MP3 is made in a second step after the download reaches
     100%; the box says "making the MP3 file... please wait".
     That takes a little longer, so wait for "Done!".
     Sound needs the helper module (FFmpeg). If it is missing, the
     program says so and nothing is downloaded. Press the
     "Install helper" button next to the message, wait until it
     says the helper is installed, then press "Download sound"
     again.
     The choice is not remembered: the program always starts on
     "Video". It applies to this main screen only. The scan page
     and the webinar room page always save video; each page says so.
  6. Wait. The box at the bottom of the window shows how far
     along it is and roughly how many minutes are left.
  7. When it says "Done! The video is saved." (or "Done! The sound
     is saved as an MP3 file."), press the blue "Open folder"
     button next to it to see the file.

WHERE THE VIDEOS GO
-------------------
The line "Videos are saved in:" shows the folder - usually
your Downloads folder. "Open folder" opens it, "Change" picks
another one. The choice is remembered next time.

COURSE PAGES WITH SEVERAL VIDEOS
--------------------------------
Some course websites (for example schools built on GetCourse, and
players called Kinescope) hide their videos inside the page. Copy
the lesson page's address and press the green button as usual:
the program finds the videos itself and downloads all of them.
Each video is saved under its own title when the player gives
one, otherwise as "lesson-name - 1", "lesson-name - 2", ...
For a private lesson, set up "Log in to websites" first (section
5) - without the login file the page shows no videos at all.
The first message under the link tells how many videos it found.
Long lessons are big files: a lecture of several hours can take a
long time and a lot of disk space.

VK LIVE BROADCASTS
------------------
Links that look like  vkvideo.ru/live-123_456  (a live broadcast or
its recording) work like any other VK video: paste the link and
press the green button. VK sometimes shows a "bot check" instead
when it gets many requests in a row; if that happens, wait a few
minutes and try again.

CONVERTING A RECORDING TO MP4
-----------------------------
If you recorded a live broadcast with another program, the file is
often a ".mkv" or ".ts" file. Some players and phones cannot open
those. Press "Convert to MP4" (below the folder line), pick the
recording, and the program makes a normal .mp4 file next to it.

  * Picture and sound are copied, not re-made, so there is no loss
    of quality and a long recording takes only a minute or two.
  * The original file is never changed or deleted, and an existing
    file is never overwritten (the new one gets "(1)" in its name).
  * Do not convert a recording while it is still being recorded;
    wait until the broadcast has ended.

RECORDING A LIVE WEBINAR ROOM
-----------------------------
Some schools give you a link to a live webinar "room" (the web
address contains /room/ , for example online.example.ru/room/abc).
The video is not on the page, so the normal download cannot get
it. The program can record the broadcast while it runs and turn
it into an MP4 for you.

  1. At the bottom of the window, click
       "Record a webinar room"
  2. Copy the link you received for the webinar (in an e-mail or
     on the course page - it is your own personal link, do not
     share it) and press "Paste link".
  3. Press the green "Start recording". You can do this before
     the webinar begins: the program says "Waiting for the
     broadcast to begin" and starts recording by itself.
  4. Keep the window open. The "Start recording" button turns
     grey and the red "Stop and save" button becomes active.
     The window shows how much has been recorded (hours:minutes:
     seconds). The program asks Windows not to go to sleep
     while it works, but do not close the laptop lid and plug in
     the charger. If the computer sleeps anyway, the recording
     stops or has a gap.
  5. When the webinar is over, the program stops by itself and
     makes the MP4. To finish earlier, press "Stop and save".
     Wait for "Done!". The MP4 is in your download folder.

  * Normally only the ".mp4" is left: the program checks that it
    is as long as the raw recording and then removes the raw
    ".ts" file. If anything looks wrong (pieces missing, a
    different length), it keeps the ".ts" too and the final
    message says so; play the .mp4 before you delete the .ts.
  * If you start late, the program records the broadcast from its
    very beginning, not from the moment you pressed the button.
  * If the school sends no video for more than 3 minutes (for
    example a long break, or the broadcast broke off), the
    program decides it is over, saves what it has and stops. After
    a break, start a new recording.
  * The final message says how it ended. If some short pieces
    could not be downloaded, it says so (the video may jump).
  * While the program is only waiting for the broadcast to begin,
    "Stop and save" simply cancels.
  * If you close the window during a recording, the program asks
    first. If you close it anyway, or switch the computer off, the
    recording stops and no MP4 is made. The ".ts" file stays in
    the folder: use "Convert to MP4" on it.
  * This works only for a webinar that is on air now or starts
    soon. A webinar that is already over cannot be recorded.
  * The program needs its helper module (FFmpeg) for the MP4. If
    it is missing, the program offers "Install helper".
  * The program uses the personal part of the link only to enter
    the room as you; it does not save it anywhere.
  * A recording is big: about 2 GB per hour. A two-hour webinar
    needs about 4 GB for the raw ".ts" file and about 4 GB more for
    the ".mp4" while it is being made, so keep about 8 GB free
    on the disk.
  * Only rooms whose video comes from the Rutube website are
    supported so far (you cannot tell from the link; just try,
    the program will say so). For another kind it shows a code:
    tell the person who helps you and give them that code.

LANGUAGE
--------
The button in the top right corner switches the program
between English and Russian ("Русский" / "English"). The
choice is remembered. On a computer set up in Russian the
program starts in Russian by itself.


---------------------------------------------------------------
  4. SEVERAL VIDEOS ON ONE PAGE
---------------------------------------------------------------

Online courses often put five or six videos on a single page.
This collects them all at once.

  1. At the bottom of the window, click
       "Several videos on one page"
  2. Copy the address of the page (not of one video) and
     press "Paste link"
  3. Press "Find videos"
  4. A list appears, every video already ticked
  5. Click any line to untick what you do not want
  6. Press the green "Download ticked videos" button
  7. "Back" returns to the main screen

Note: use the address of a REAL page, not just the website's
front page. For example a specific course lesson, or a specific
channel - not just "vk.com".

A LIST OF LINKS IN A FILE
-------------------------
Instead of scanning a page, press "Open list file..." and pick
a file with video links:

  .txt   one link per line. Text before a link on the same line
         becomes the video's name, for example
            Week 1 - Introduction: https://.../lecture1.mp4
         The name may also be on the line above the link - the
         files saved by Coursera Link Collector work as they are.
  .json  a list of links, or of entries with "url" and "title"

The videos appear in the list, ticked. With names from the file
they are saved in order as "01 - Week 1 - Introduction.mp4",
"02 - ...". The number is the video's place in the file, so
unticking one does not change the others; a name that already
starts with a number (like "03 Installing ...") keeps it as is.
Download links from course websites often stop
working after a few hours - download them on the same day.


---------------------------------------------------------------
  5. LOG IN TO WEBSITES  (only if a video refuses to download)
---------------------------------------------------------------

Most videos need nothing special. But private videos, paid
courses and age-restricted videos only work if the downloader
can prove you are logged in. That proof is a small "login
file" (its technical name is cookies.txt).

You make one once. It then works for months.

WHAT TO DO
----------
  1. At the bottom of the window, click "Log in to websites"
  2. Press "Open add-on page" - your browser opens
  3. Install the add-on called "Get cookies.txt LOCALLY"
       (click "Add to Chrome" or "Add to Edge", then confirm)
  4. Back in Video Downloader, press "Open websites"
  5. Open each site you use and LOG IN to it
       - do them all now, in the same browser
  6. Click the add-on's icon in the browser toolbar
       (top right, may be hidden behind a puzzle-piece icon)
  7. Click "Export"

That is it. Video Downloader notices the file by itself and
says "Login file found". You do not need to find the file.

IMPORTANT
---------
  * Do ALL the sites in one go, then export ONCE. One file
    covers every site you were logged in to.
  * Do NOT log out of those websites afterwards. Logging out
    cancels the login file too. Just close the tab.
  * After some months downloads may start failing again. That
    means the login file got old. Repeat steps 6 and 7.
  * The login file is a key to your accounts. Do not send it
    to anyone.


---------------------------------------------------------------
  6. IF SOMETHING GOES WRONG
---------------------------------------------------------------

Problems are explained in plain words in the box at the bottom
of the window. Often there is a blue button next to the
message that does the fix - just press it.

"This video is private" / "YouTube wants proof you are a person"
  -> Press the "Log in to websites" button and follow
     section 5. If you already did it, the login file is old:
     click the add-on and Export again.

"YouTube refused the download"
  -> Press "Update now". When it says "Updated", close the
     program, open it again and try once more.

"A helper module (FFmpeg) is missing"
  -> Press "Install helper" and wait a few minutes.

"No internet connection, or the website is not answering"
  -> Check the internet, wait a minute, press Download again.

"No video was found on this page"
  -> Either the page is a private lesson - press "Log in to
     websites" and follow section 5, then try again - or this
     website is not supported, or the address is not the page
     where the video plays.

"Done! 2 of 3 videos saved"
  -> A page with several videos was downloaded, but one of them
     failed. The others are saved. Press the green button again
     to retry; videos that are already saved are not downloaded
     twice.

"This address is not a video page"
  -> Copy the address again - make sure it is the page where
     the video plays, not the website's front page.

Nothing happens when I double-click
  -> Make sure you are double-clicking  VideoDownloader.bat  and
     that VideoDownloader.py is in the same folder.

The black window flashes and disappears
  -> Something failed too fast to read. See section 7.

It says Python was installed but asks me to restart
  -> Restart the computer and double-click VideoDownloader.bat
     again. This only happens once.

The download stops partway
  -> Usually the internet connection. Just press Download
     again; it picks up from where it stopped.

Videos look blurrier than expected
  -> That is normal. This tool is set to 480p on purpose, so
     files stay small.

Something else
  -> See section 7, then send the result to whoever set this up
     for you.


---------------------------------------------------------------
  7. THE SELF TEST AND "DETAILS FOR HELPER"
---------------------------------------------------------------

DETAILS FOR HELPER
------------------
The link "Details for helper" at the bottom of the window shows
what is working, the versions, a few expert settings, buttons to
update the download engine or install the helper module (FFmpeg), and a
log of everything the program did. A helper can read the reason
for a failed download there.

THE SELF TEST
-------------
If you need help, run this. It checks everything and prints a
report.

  1. Hold SHIFT and right-click the folder with the files
  2. Choose "Open PowerShell window here" or
     "Open command window here"
  3. Type this and press Enter:

        .\VideoDownloader.bat --selftest

  4. Wait for it to finish, then select all the text, copy it,
     and send it to the person helping you.

There is also a log file:
    %LOCALAPPDATA%\VideoDownloader\VideoDownloader.log
(paste that line into the address bar of any folder window).


---------------------------------------------------------------
  8. THINGS WORTH KNOWING
---------------------------------------------------------------

Does it cost anything?
  No. Every part of it is free.

Does it send my passwords anywhere?
  No. The login file stays on your own computer. The add-on
  called "Get cookies.txt LOCALLY" is named that because it does
  the work locally, without uploading anything.

Why 480p and not full quality?
  480p is clear enough on a laptop or tablet while keeping files
  small and downloads quick.

Does it update itself?
  Yes. Websites change often, so it quietly updates its own
  downloading engine every time you start it.

Does it look at what I copy?
  Only when you switch to its window, and only a web address:
  it puts the address in the box and checks it. It never
  downloads anything until you press the green button.

Is it all right to download this?
  This program is a tool, like a video recorder. What you may
  do with a recording depends on the video, the website and
  the law of your country - and it is your own responsibility.
  The rules below are general guidance, not legal advice.
  * Saving a video for your own private viewing (to watch
    without internet, to study a course you have paid for or
    been given access to) is what this program is made for.
    In some countries the law allows such private copies; in
    others it does not. "Fair use" is a United States rule and
    does not apply everywhere.
  * Do not publish, sell or share what you save, and do not
    upload it to another website. The video still belongs to
    whoever made it.
  * Use only your own login. Never use another person's
    login file, and never pass your own login file on.
  * The program does not break copy protection. If a video is
    encrypted, it simply fails (see section 9).
  * A website may forbid downloading in its terms of use. If
    in doubt, ask the owner of the video for permission.


---------------------------------------------------------------
  9. WHAT IT CANNOT DO
---------------------------------------------------------------

  * Netflix, Disney+, Amazon Prime and similar services are
    encrypted and cannot be downloaded by any tool. Nothing is
    broken - it is simply not possible.
  * It always downloads in 480p. There is no setting for higher
    quality.
  * A website can change overnight and stop working until the
    download engine catches up (usually within days). Starting
    the program again the next day often fixes it.
  * Windows only. There is no version for Mac or Linux.
  * Webinar rooms: only rooms whose video comes from Rutube, and
    only while you keep the window open and the computer awake. It cannot record a room
    whose link has expired or that needs a password you do not
    have. A webinar that has already ended and was not recorded
    by the school cannot be recovered.


---------------------------------------------------------------
  10. FILES IN THIS PACKAGE
---------------------------------------------------------------

  VideoDownloader.bat   Starts the program; installs Python and
                        the download engine on the first run.
  VideoDownloader.py    The program itself.
  README.txt            This file.

Created on your computer while you use it:
  .video_downloader.json  in your user folder - remembers your
                          download folder and language.
  VideoDownloader.log     in %LOCALAPPDATA%\VideoDownloader -
                          messages for troubleshooting.


---------------------------------------------------------------
  QUICK REFERENCE
---------------------------------------------------------------

  Normal use ............ double-click  VideoDownloader.bat
  Check for problems .... .\VideoDownloader.bat --selftest
  One video, no window .. .\VideoDownloader.bat --url "LINK"

===============================================================
