"""Core planning engines: media, VLSM, topology, routing, and switching.

The core package deliberately has no web imports and does not import Python's
``ipaddress`` module for allocation.  All IPv4 arithmetic is bitwise so the
masks and alignments in the report are the ones the engine actually computed.
"""
