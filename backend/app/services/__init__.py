"""Application services: orchestration, and nothing else.

A service coordinates. It reads from repositories, calls the domain, writes
back, records an audit entry. The moment a service starts deciding whether a
balance sheet balances, that decision belongs in ``domain/`` instead.
"""
