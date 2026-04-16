"""Monitoring and alerting system"""


class MonitoringAlert:
    """Monitor pipeline metrics and fire alerts."""

    def __init__(self, plugins: list, thresholds: dict = None):
        self.plugins = plugins
        self.thresholds = thresholds or {
            "block_rate": 0.3,  # Alert if >30% requests blocked
            "rate_limit_rate": 0.2,  # Alert if >20% rate limited
            "judge_fail_rate": 0.15,  # Alert if >15% fail judge
        }

    def check_metrics(self):
        """Check all metrics and fire alerts."""
        print("\n" + "=" * 60)
        print("MONITORING REPORT")
        print("=" * 60)

        alerts = []

        for plugin in self.plugins:
            if hasattr(plugin, "total_count") and plugin.total_count > 0:
                blocked = getattr(plugin, "blocked_count", 0)
                rate = blocked / plugin.total_count
                print(f"\n{plugin.name}:")
                print(f"  Total: {plugin.total_count}")
                print(f"  Blocked: {blocked} ({rate:.1%})")

                # Check thresholds
                if (
                    plugin.name == "rate_limiter"
                    and rate > self.thresholds["rate_limit_rate"]
                ):
                    alerts.append(
                        f"⚠️  HIGH RATE LIMIT: {rate:.1%} of requests rate-limited"
                    )
                elif plugin.name in [
                    "input_guardrail",
                    "output_guardrail",
                ] and rate > self.thresholds["block_rate"]:
                    alerts.append(f"⚠️  HIGH BLOCK RATE ({plugin.name}): {rate:.1%}")

        if alerts:
            print("\n" + "=" * 60)
            print("🚨 ALERTS:")
            for alert in alerts:
                print(f"  {alert}")
        else:
            print("\n✅ All metrics within normal range")

        print("=" * 60)
