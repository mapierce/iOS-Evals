// swift-tools-version: 6.0
import PackageDescription

// Minimal compile unit for one generated sample.
// Must build at zero warnings before any model output is inserted — scaffold
// noise would be counted against every model. See tests/test_scaffold.py.
let package = Package(
    name: "Sample",
    platforms: [.iOS(.v17)],
    products: [
        .library(name: "Sample", targets: ["Sample"])
    ],
    targets: [
        .target(
            name: "Sample",
            path: "Sources/Sample"
        )
    ]
)
