# MVI and state

Feature ViewModels are internal and extend `BaseViewModel<State, Event, Intent>`.

- `initialState()` returns a trivial default and never reads injected dependencies.
- State is an immutable data class or sealed interface; annotate state variants with `@Immutable`.
- Intent is a nested sealed interface.
- Every `handleIntent` branch calls one private function.
- Use the `launch {}` extension for coroutine work, not direct `viewModelScope.launch`.
- Inject dispatchers used for business work.
- Expose display-ready strings and UI models; keep formatting out of composables.
- Collect with `collectAsStateWithLifecycle()` and register lifecycle-aware ViewModels from screen setup.
- Model dialogs/sheets as state and one-shot effects through the event flow.

Screens render state and forward intents. They do not reach into repositories, formatters, navigation controllers, or DI graphs.
