class AgentError(Exception):
    """Raised for expected/user-facing agent errors (e.g. invalid input).

    `user_facing=True` (default) means the message is safe to show to the
    end user as-is. Set False for internal errors whose raw message
    shouldn't be surfaced directly.
    """

    def __init__(self, message: str, user_facing: bool = True):
        super().__init__(message)
        self.user_facing = user_facing
