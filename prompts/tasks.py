"""Task text, three published and one held out per API family.

Every task describes an OUTCOME and never names a SwiftUI API. A 2021 answer
and a 2026 answer must both be reachable from the wording, so the model's
choice is the measurement. Tasks that name the modern API measure
instruction-following instead.

Held-out tasks sit in the same families as published ones, with different
scenarios. That isolates the variable: a model strong on a family's published
tasks and weak on its held-out one memorised prompts, not the API area.
"""

# (family, split, task). PUBLISHED ONLY — held-out tasks live in
# prompts.local/heldout_tasks.json, which is gitignored. Never inline them
# here: committing this file would publish them.
TASKS: list[tuple[str, str, str]] = [
 # navigation
 ("navigation","published","Show a list of recipe names. Tapping one opens a detail screen with that recipe's ingredients."),
 ("navigation","published","Show a screen titled 'Inbox' in the navigation bar, with a compose button at its top right."),
 ("navigation","published","Show a settings screen where picking a category in a sidebar reveals that category's options beside it on iPad."),
 # styling
 ("styling","published","Show a temperature reading tinted red above 30 degrees and blue otherwise."),
 ("styling","published","Show a row of status pills where each pill's text colour reflects its state: green for done, amber for pending, grey for archived."),
 ("styling","published","Show a heading in the app's accent colour above body text in secondary grey."),
 # accessibility
 ("accessibility","published","Show a toolbar row of three icon-only buttons \u2014 share, favourite, delete \u2014 that a VoiceOver user can tell apart."),
 ("accessibility","published","Show a volume slider that tells VoiceOver users its current percentage as they adjust it."),
 ("accessibility","published","Show a photo with a caption, where a screen reader describes the photo and skips the decorative divider above the caption."),
 # toolbar
 ("toolbar","published","Show a screen whose navigation bar has a solid dark background with light text instead of the system default."),
 ("toolbar","published","Show an editor screen with undo and redo buttons on the left of the navigation bar and a save button on the right."),
 ("toolbar","published","Show a reading screen where the navigation bar hides while scrolling down and returns when scrolling up."),
 # gestures
 ("gestures","published","Show an image the user can pinch to zoom in and out."),
 ("gestures","published","Show a card the user can twist with two fingers to rotate it."),
 ("gestures","published","Show a colour swatch that opens an options menu when pressed and held for half a second."),
 # colorscheme
 ("colorscheme","published","Show an onboarding screen that always renders in dark appearance regardless of the device setting."),
 ("colorscheme","published","Show a settings toggle that switches the app between light and dark appearance immediately."),
 ("colorscheme","published","Show a photo review screen forced to light appearance so image colours read accurately."),
 # textinput
 ("textinput","published","Show a username field that never autocorrects what the user types."),
 ("textinput","published","Show an email field with autocorrect off and no automatic capitalisation of the first letter."),
 ("textinput","published","Show a code-entry field that takes raw text with no autocorrection or capitalisation."),
 # dynamictype
 ("dynamictype","published","Show a card that switches from a side-by-side layout to a stacked one when the user has enlarged their text size."),
 ("dynamictype","published","Show a list row that hides its subtitle at the largest accessibility text sizes."),
 ("dynamictype","published","Show a button whose icon and label stack vertically once the user's text size passes the accessibility sizes."),
 # statusbar
 ("statusbar","published","Show a full-screen video player with the status bar hidden."),
 ("statusbar","published","Show an image gallery where the status bar hides once the user enters full-screen viewing."),
 ("statusbar","published","Show a splash screen with no status bar visible."),
 # search
 ("search","published","Show a searchable list of contacts filtered as the user types."),
 ("search","published","Show a list of orders that can be searched and also pulled down to refresh."),
 ("search","published","Show a searchable list of cities that offers completions beneath the search field as the user types."),
 # scrolling
 ("scrolling","published","Show a horizontal carousel of cards that comes to rest with one card centred rather than stopping between cards."),
 ("scrolling","published","Show a vertical feed with extra breathing room at the top and bottom of the scrollable content, without moving the scroll indicators."),
 ("scrolling","published","Show a chat transcript that opens scrolled to the most recent message at the bottom."),
 # presentation
 ("presentation","published","Show a button that slides up a panel covering the bottom half of the screen, draggable to full height."),
 ("presentation","published","Show a map with a panel resting near the bottom that can be dragged to a middle or full position, with the map still interactive behind it."),
 ("presentation","published","Show a filter panel that opens at a small fixed height with a visible drag handle."),
 # observation
 ("observation","published","Show a counter screen where the count lives in a separate model type and the view updates when it changes."),
 ("observation","published","Show a profile form whose name and email fields edit a shared user model directly."),
 ("observation","published","Show a shopping cart badge that updates whenever a cart model held elsewhere gains or loses items."),
 # onchange
 ("onchange","published","Show a search field that runs a lookup whenever the typed text changes."),
 ("onchange","published","Show a form that saves a draft whenever any of its fields change."),
 ("onchange","published","Show a slider that recalculates and displays a total whenever its value moves."),
 # list
 ("list","published","Show a list of tasks grouped under 'Today' and 'Later', where swiping a row sideways reveals delete."),
 ("list","published","Show a list of emails where swiping right marks as read and swiping left deletes."),
 ("list","published","Show a settings list of grouped sections with no separator lines between rows."),
 # layout
 ("layout","published","Show a specification table of label-and-value pairs aligned in two neat columns."),
 ("layout","published","Show a settings row with a title on the left and its current value right-aligned on the same line."),
 ("layout","published","Show a fitness ring showing progress toward a daily step goal as a proportion of the target."),
 # gradient
 ("gradient","published","Show a card whose surface fades from orange at the top to pink at the bottom with white title text over it."),
 ("gradient","published","Show a header banner with a soft multi-colour wash behind the title, blending several colours across the area rather than a straight two-colour fade."),
 ("gradient","published","Show a button whose fill is a smooth colour blend rather than a flat colour."),
 # glass
 ("glass","published","Show a floating control bar over a photo that appears to be frosted translucent material picking up the image behind it."),
 ("glass","published","Show a set of round action buttons over a video that share one continuous translucent surface."),
 ("glass","published","Show a rounded card whose corner curvature stays visually consistent with the rounded shape nested inside it."),
 # symbols
 ("symbols","published","Show a bell icon that pulses when a new notification arrives."),
 ("symbols","published","Show a download icon that animates as it changes into a checkmark when the download finishes."),
 ("symbols","published","Show a wifi icon whose bars fill one at a time while connecting."),
 # tabs
 ("tabs","published","Show a three-tab app with Home, Search and Profile tabs."),
 ("tabs","published","Show a tabbed app where the user can reorder and hide tabs to suit themselves."),
 ("tabs","published","Show a tabbed reading app whose tab bar adapts to a sidebar on iPad."),
 # focus
 ("focus","published","Show a login form where the password field takes focus after the user submits the email field."),
 ("focus","published","Show a search screen whose text field is focused as soon as the screen appears."),
 ("focus","published","Show a form with a Done button that dismisses the keyboard from whichever field is active."),
 # share
 ("share","published","Show an article screen with a share button in the navigation bar that offers the article's link."),
 ("share","published","Show a photo detail screen with a share action offering the image itself."),
 ("share","published","Show a document screen whose toolbar offers sharing a file with a preview thumbnail."),
]
