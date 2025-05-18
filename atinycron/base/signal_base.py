# -*- coding: UTF-8 -*-
import logging
import signal
import types

logger = logging.getLogger('atinycron')

_SHUTDOWN_SIGNALS = frozenset({
    signal.SIGINT,
    signal.SIGTERM,
    signal.SIGQUIT,
})


class ShutdownSignalHolder:

    def __init__(self):
        self._current_signal = list()
        for sig in _SHUTDOWN_SIGNALS:
            signal.signal(signalnum=sig, handler=self.set_signal)

    @property
    def shutdown_signal_received(self) -> bool:
        if self._current_signal:
            logger.debug('All received signals: %s', self._current_signal)
            matched_signals = set(self._current_signal) & _SHUTDOWN_SIGNALS
            if matched_signals:
                logger.debug('matched signals: %s', matched_signals)
                return True
        return False

    def set_signal(self, received_signal: int, frame: types.FrameType) -> None:
        logger.info('Signal %s received.', received_signal)
        logger.debug('set_signal called with frame: %s', frame)
        self._current_signal.append(received_signal)
