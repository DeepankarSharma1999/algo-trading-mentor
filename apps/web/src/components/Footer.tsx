/** Every screen carries this line. The synthetic clause only appears while SyntheticProvider is active. */
export function Footer({ provider }: { provider: string }) {
  return (
    <footer className="footer-note" data-testid="footer">
      Educational tool. Not SEBI-registered. No recommendations.{provider === "synthetic" ? " Synthetic data." : ""}
    </footer>
  );
}
