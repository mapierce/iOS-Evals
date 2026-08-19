"""API families with real churn, derived from the ground truth artifact.

Not hand-recalled. Each family's stale/current symbols come from the
@available parse: `stale` symbols carry a deprecation, `current` symbols are
their replacements or the modern surface for that area. Every name here is
asserted against ground truth by build_corpus.py before anything is written.

A family needs BOTH a stale symbol a model might reach for AND a current
replacement, otherwise a prompt built on it cannot distinguish an outdated
answer from a current one.
"""

FAMILIES: dict[str, dict[str, list[str]]] = {
    # --- deprecation-driven: the compiler reports these directly ---
    "navigation": {
        "gate": ["NavigationView", "NavigationStack", "NavigationLink",
                 "navigationDestination", "NavigationSplitView", "NavigationPath",
                 "navigationBarTitle", "navigationTitle"],
        "stale": ["NavigationView", "navigationBarTitle"],
        "current": ["NavigationStack", "navigationDestination", "navigationTitle",
                    "NavigationSplitView", "NavigationPath"],
    },
    "styling": {
        "gate": ["foregroundColor", "foregroundStyle", "background", "backgroundStyle"],
        "stale": ["foregroundColor"],
        "current": ["foregroundStyle", "backgroundStyle"],
    },
    "accessibility": {
        "gate": ["accessibility", "accessibilityLabel", "accessibilityValue",
                 "accessibilityHidden", "accessibilityAddTraits"],
        "stale": ["accessibility"],
        "current": ["accessibilityLabel", "accessibilityValue", "accessibilityHidden",
                    "accessibilityAddTraits"],
    },
    "toolbar": {
        "gate": ["toolbar", "ToolbarItem", "ToolbarItemGroup", "toolbarBackground",
                 "toolbarColorScheme"],
        "stale": ["toolbar", "toolbarBackground"],
        "current": ["ToolbarItem", "ToolbarItemGroup", "toolbarColorScheme"],
    },
    "gestures": {
        "gate": ["MagnificationGesture", "MagnifyGesture", "RotationGesture",
                 "RotateGesture", "onLongPressGesture"],
        "stale": ["MagnificationGesture", "RotationGesture", "onLongPressGesture"],
        "current": ["MagnifyGesture", "RotateGesture"],
    },
    "colorscheme": {
        "gate": ["colorScheme", "preferredColorScheme"],
        "stale": ["colorScheme"],
        "current": ["preferredColorScheme"],
    },
    "textinput": {
        "gate": ["disableAutocorrection", "autocorrectionDisabled",
                 "textInputAutocapitalization"],
        "stale": ["disableAutocorrection"],
        "current": ["autocorrectionDisabled", "textInputAutocapitalization"],
    },
    "dynamictype": {
        "gate": ["sizeCategory", "ContentSizeCategory", "dynamicTypeSize", "DynamicTypeSize"],
        "stale": ["sizeCategory", "ContentSizeCategory"],
        "current": ["dynamicTypeSize", "DynamicTypeSize"],
    },
    "statusbar": {
        "gate": ["statusBar", "statusBarHidden"],
        "stale": ["statusBar"],
        "current": ["statusBarHidden"],
    },
    "search": {
        "gate": ["searchable", "refreshable"],
        "stale": [],
        "current": ["searchable", "refreshable"],
    },

    # --- availability-driven: above the pinned target, so hard compile errors ---
    "scrolling": {
        "gate": ["ScrollView", "scrollTargetBehavior", "scrollTargetLayout",
                 "scrollPosition", "contentMargins", "safeAreaPadding",
                 "defaultScrollAnchor", "scrollClipDisabled", "scrollIndicators"],
        "stale": [],
        "current": ["scrollTargetBehavior", "scrollTargetLayout", "scrollIndicators"],
    },
    "presentation": {
        "gate": ["sheet", "presentationDetents", "presentationDragIndicator",
                 "presentationBackground", "presentationSizing"],
        "stale": [],
        "current": ["presentationDetents", "presentationDragIndicator",
                    "presentationBackground"],
    },
    # "observation" removed: the family is entirely property-wrapper based
    # (@State, @StateObject, @Bindable), and the parse-only AST records those
    # as nameless attribute nodes. Its gate could never fire, so every sample
    # scored as ungated regardless of what the model wrote. See the known
    # limitations in docs/metrics.md.
    "onchange": {
        "gate": ["onChange", "task", "onAppear", "State"],
        "stale": [],
        "current": ["onChange", "task"],
    },
    "list": {
        "gate": ["List", "ForEach", "Section", "swipeActions", "listRowSeparator"],
        "stale": [],
        "current": ["swipeActions", "Section", "listRowSeparator"],
    },
    "layout": {
        "gate": ["Grid", "GridRow", "LabeledContent", "GroupBox", "Gauge"],
        "stale": [],
        "current": ["Grid", "GridRow", "LabeledContent", "Gauge"],
    },
    "gradient": {
        "gate": ["MeshGradient", "backgroundStyle", "background", "foregroundStyle",
                 "foregroundColor"],
        "stale": ["foregroundColor"],
        "current": ["MeshGradient", "backgroundStyle", "foregroundStyle"],
    },
    "glass": {
        "gate": ["glassEffect", "GlassEffectContainer", "ConcentricRectangle", "background"],
        "stale": [],
        "current": ["glassEffect", "GlassEffectContainer", "ConcentricRectangle"],
    },
    "symbols": {
        "gate": ["symbolEffect", "contentTransition", "Image"],
        "stale": [],
        "current": ["symbolEffect", "contentTransition"],
    },
    "tabs": {
        "gate": ["TabView", "Tab", "tabViewStyle"],
        "stale": [],
        "current": ["Tab", "tabViewStyle"],
    },
    "focus": {
        "gate": ["FocusState", "focused", "State"],
        "stale": [],
        "current": ["FocusState", "focused"],
    },
    "share": {
        "gate": ["ShareLink", "toolbar", "ToolbarItem"],
        "stale": ["toolbar"],
        "current": ["ShareLink", "ToolbarItem"],
    },
}
