# Measurement methodology

1. Record machine, JDK, and Gradle version context in the artifact environment block.
2. Use identical scenario commands for baseline and current.
3. Run warmups separately; exclude them from medians.
4. Prefer odd measured run counts (3 or 5) and report medians.
5. Capture task states from Gradle’s actionable-task summary when present.
6. Note configuration-cache reuse when the build prints it.
7. Do not claim significance from a single measured run.
