def run(self, client_id: str, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
        profile = load_client_profile(client_id)
        overrides = overrides or {}

        # Merge – request wins
        for k in ("name", "goals", "risk", "horizon"):
            if overrides.get(k) is not None:
                profile[k] = overrides[k]

        client_name = profile.get("name") or profile.get("client_id", client_id)

        # 1) Portfolio assessment
        pm = self.portfolio_monitor.run(client_id=client_id, client_name=client_name)

        # 2) Recommendations use the merged profile
        rec = self.recommender.run(profile=profile, score=pm["score"])

        # 3) Final pitch
        pitch = self.pitch_writer.run(
            client_name=client_name,
            findings=pm["summary"],
            recos_bullets=rec["bullets"]
        )

        return {
            "client": profile,            # <-- merged profile returned
            "portfolio": pm,
            "recommendations": rec,
            "pitch": pitch["pitch"]
        }
