export interface LegalDoc {
  slug: "privacy" | "terms" | "cookies";
  title: string;
  updated: string;
  intro: string;
  sections: { heading: string; body: string[] }[];
}

const NOTE =
  "This service is a demonstration product. These terms describe how the demonstration environment works.";

export const LEGAL: LegalDoc[] = [
  {
    slug: "privacy",
    title: "Privacy policy",
    updated: "2026-11-01",
    intro:
      "This policy explains what personal data the Provenance Risk demonstration environment collects, why, how long it is kept, and what choices you have. " +
      NOTE,
    sections: [
      {
        heading: "Who is responsible",
        body: [
          "The operator of this demonstration environment is the controller of the personal data described here. Contact the operator at the address on the company page.",
        ],
      },
      {
        heading: "What we collect",
        body: [
          "Demonstration requests: name, work email, organization, role, industry, message, and a record of your consent.",
          "Newsletter: your email address, and the time you confirmed the subscription. A confirmation email is sent first, and you are subscribed only after you confirm.",
          "Accounts: email address, role, a hashed password, multi-factor enrollment data (the secret is stored encrypted and recovery codes are stored hashed), sign-in times, and session details such as the browser description.",
          "Security records: an audit log of sign-ins, changes to users and keys, and review decisions, with the network address from which a request was made.",
          "Customer data: supplier lists and the results of resolving them, which belong to the customer and are isolated by tenant.",
        ],
      },
      {
        heading: "Why we use it",
        body: [
          "To respond to demonstration requests and to send the newsletter you confirmed.",
          "To provide and secure accounts, including detecting repeated failed sign-ins.",
          "To keep an audit trail that lets a customer see who did what.",
          "We do not sell personal data and we do not use it for advertising.",
        ],
      },
      {
        heading: "Training data",
        body: [
          "Reviewer decisions are used to improve matching models only when a customer has opted in. Opted-in examples are stored without any customer identifier.",
        ],
      },
      {
        heading: "Retention",
        body: [
          "Each customer has a retention period for its data, with a default of 730 days. Demonstration requests and newsletter records are kept until you ask us to delete them or we close the demonstration. The scheduled job that enforces retention is not yet running, so deletion is currently done on request.",
        ],
      },
      {
        heading: "Sharing",
        body: [
          "Email is sent through the operator's mail service. Data is not shared with advertisers. If the operator uses a hosting provider, that provider processes data on the operator's instructions.",
        ],
      },
      {
        heading: "Your rights",
        body: [
          "Depending on where you live, you may have the right to access, correct, delete, restrict, or export your personal data, and to object to processing. Write to the contact address and we will respond within the period required by law. You can withdraw newsletter consent at any time.",
        ],
      },
      {
        heading: "Security",
        body: [
          "Traffic is encrypted. Sensitive identifiers are encrypted at rest. Access is controlled by roles, and administrators must use multi-factor sign-in. See the security page for the measures and for what is not claimed.",
        ],
      },
      {
        heading: "Changes",
        body: ["We will update this page and its date when the policy changes."],
      },
    ],
  },
  {
    slug: "terms",
    title: "Terms of use",
    updated: "2026-11-01",
    intro: "These terms govern access to the Provenance Risk demonstration environment. " + NOTE,
    sections: [
      {
        heading: "Acceptance",
        body: [
          "By using the site or a demonstration account you agree to these terms. If you do not agree, do not use the service.",
        ],
      },
      {
        heading: "Demonstration status",
        body: [
          "The environment contains demonstration data. Revenue, usage, portfolio, and tenant figures are synthetic. Prices are illustrative and no payment is collected. The service is provided without commitments on availability or support.",
        ],
      },
      {
        heading: "Accounts",
        body: [
          "You are responsible for the activity of your account and for keeping credentials and multi-factor devices secure. Tell us promptly if you suspect misuse.",
        ],
      },
      {
        heading: "Acceptable use",
        body: [
          "Do not attempt to access another customer's data, probe the service for vulnerabilities without written permission, overload it, or use it to harass or defame any person or business.",
          "Do not use risk signals as the sole basis for an adverse decision about a business or person.",
        ],
      },
      {
        heading: "Nature of the information",
        body: [
          "Risk signals are leads for human review and not statements of fault. The service reports what public records say, with their source and date. It does not determine that any company broke a law or caused an incident. Records can be incomplete, outdated, or linked to the wrong company, and matching is probabilistic.",
        ],
      },
      {
        heading: "Third-party data and models",
        body: [
          "The service uses public data from the sources listed on the methodology page, each under its own terms. The project builds on open-source BELA and BLINK releases and is not affiliated with their authors. Publishers keep the copyright in news content, and the service stores metadata and snippets.",
        ],
      },
      {
        heading: "Your data",
        body: [
          "You keep the rights in the data you upload. You grant the operator permission to process it to provide the service. Opt-in sharing of reviewer decisions for model improvement is off by default.",
        ],
      },
      {
        heading: "Disclaimer and liability",
        body: [
          "To the extent permitted by law, the service is provided as is, without warranties of any kind, and the operator is not liable for indirect or consequential loss arising from its use. Nothing in these terms limits liability that cannot be limited by law.",
        ],
      },
      {
        heading: "Changes and termination",
        body: [
          "We may change these terms or end the demonstration. We will update this page when terms change. You may stop using the service at any time.",
        ],
      },
    ],
  },
  {
    slug: "cookies",
    title: "Cookie policy",
    updated: "2026-11-01",
    intro:
      "This page lists the cookies and similar storage used by the Provenance Risk demonstration site. " +
      NOTE,
    sections: [
      {
        heading: "Essential cookies only",
        body: [
          "The site uses cookies that are needed to sign in and to protect your session. It does not set advertising or analytics cookies, and it does not load third-party trackers.",
        ],
      },
      {
        heading: "Cookies set when you sign in",
        body: [
          "pr_access: a short-lived signed token that proves who you are. It cannot be read by scripts on the page (HttpOnly) and is sent only over HTTPS (Secure).",
          "pr_refresh: an opaque token used to renew your session. HttpOnly and Secure, and it changes each time it is used.",
          "pr_csrf: a random value that the application sends back with changes, to prevent requests made from other sites. It is readable by the page by design.",
        ],
      },
      {
        heading: "Browser storage",
        body: [
          "The site stores one value, pr_cookie_notice, in your browser's local storage so that the cookie notice is not shown again after you dismiss it.",
        ],
      },
      {
        heading: "Your choices",
        body: [
          "You can delete cookies and local storage in your browser settings. Signing in will not work without the essential cookies.",
        ],
      },
    ],
  },
];

export const legalBySlug = (s: string): LegalDoc | undefined => LEGAL.find((d) => d.slug === s);
