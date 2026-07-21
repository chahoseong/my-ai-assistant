import pytest

pytestmark = pytest.mark.unit



def test_username_is_trimmed_lowercased_and_validated() -> None:
    from app.auth.security import normalize_username

    assert normalize_username("  Alice_42  ") == "alice_42"

    for invalid_username in ("ab", "a" * 51, "alice-name", "앨리스"):
        with pytest.raises(ValueError, match="Invalid username"):
            normalize_username(invalid_username)


@pytest.mark.asyncio
async def test_password_hash_round_trip_uses_argon2id() -> None:
    from app.auth.security import hash_password, verify_password

    encoded_hash = await hash_password("correct horse battery staple")

    assert encoded_hash.startswith("$argon2id$")
    assert encoded_hash != "correct horse battery staple"
    assert await verify_password(encoded_hash, "correct horse battery staple") is True


@pytest.mark.asyncio
async def test_wrong_password_returns_false() -> None:
    from app.auth.security import hash_password, verify_password

    encoded_hash = await hash_password("correct horse battery staple")

    assert await verify_password(encoded_hash, "wrong password") is False


def test_session_token_has_sufficient_entropy_and_only_hash_is_stable() -> None:
    from app.auth.security import generate_session_token, hash_session_token

    first_token = generate_session_token()
    second_token = generate_session_token()
    token_hash = hash_session_token(first_token)

    assert first_token != second_token
    assert len(first_token) >= 43
    assert token_hash == hash_session_token(first_token)
    assert len(token_hash) == 64
    assert first_token not in token_hash


@pytest.mark.asyncio
async def test_password_length_is_validated_before_hashing() -> None:
    from app.auth.security import hash_password

    with pytest.raises(ValueError, match="Invalid password"):
        await hash_password("a" * 14)

    with pytest.raises(ValueError, match="Invalid password"):
        await hash_password("a" * 129)
