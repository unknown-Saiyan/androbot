from cryptography.hazmat.primitives import serialization

key_secret ="-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEIL2nM128n+bgvB2TufeNdKV5SP4dpv1AUflISkC4A6fLoAoGCCqGSM49\nAwEHoUQDQgAEHVLusv3xCr65fVOg8S73dx0nvx8jyjUK9FcKVaMio5igaSr7nXwA\nldGg5wgzUrKo+0ckg422DoerIEDbhQtbhg==\n-----END EC PRIVATE KEY-----"

try:
    private_key = serialization.load_pem_private_key(
        key_secret.encode(), password=None
    )
    print("✅ EC key loaded successfully:", type(private_key))
except Exception as e:
    print("❌ Load error:", e)
