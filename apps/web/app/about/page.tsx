import Link from "next/link";

export const metadata = {
  title: "How it works",
};

const STEPS = [
  {
    number: "01",
    icon: "🎯",
    title: "Take an adaptive assessment",
    description:
      "Choose a skill and take a short adaptive assessment. The difficulty adjusts based on your answers — easy questions first, harder ones as you progress. Takes 15–20 minutes per skill.",
    color: "bg-primary-50 border-primary-200",
    numColor: "text-primary-600",
  },
  {
    number: "02",
    icon: "📊",
    title: "Get your competency profile",
    description:
      "Your results are scored using a deterministic algorithm — not guesswork. Each skill gets a Proficiency score (how capable you are) and a Confidence score (how strong the evidence is). These are always shown separately.",
    color: "bg-blue-50 border-blue-200",
    numColor: "text-blue-600",
  },
  {
    number: "03",
    icon: "📋",
    title: "Build your Skill Passport",
    description:
      "Add certifications, projects, and other evidence to strengthen your profile. Evidence is categorised as Claimed, Demonstrated, or Verified — so recruiters know exactly how trustworthy each skill claim is.",
    color: "bg-violet-50 border-violet-200",
    numColor: "text-violet-600",
  },
  {
    number: "04",
    icon: "📈",
    title: "See your skill gaps",
    description:
      "Select a target career role — Backend Developer, Data Engineer, and more. SkillMesh compares your current profile against the role's requirements and shows you exactly what's passing, what's a moderate gap, and what needs urgent attention.",
    color: "bg-amber-50 border-amber-200",
    numColor: "text-amber-600",
  },
  {
    number: "05",
    icon: "🛤️",
    title: "Follow a learning path",
    description:
      "Get personalised learning path recommendations based on your specific gaps — ordered by priority. Mark resources complete as you go. When you finish a path, retake the assessment to see your improved score.",
    color: "bg-emerald-50 border-emerald-200",
    numColor: "text-emerald-600",
  },
  {
    number: "06",
    icon: "🔗",
    title: "Connect with opportunities",
    description:
      "Industry partners post internships and jobs with specific skill requirements. SkillMesh matches you based on demonstrated skills — not just what you claim. Every match comes with an explainable score so you know why you were recommended.",
    color: "bg-rose-50 border-rose-200",
    numColor: "text-rose-600",
  },
];

const FOR_WHOM = [
  {
    role: "Students",
    icon: "🎓",
    points: [
      "Understand what you actually know vs what you claim",
      "Identify skill gaps before entering the job market",
      "Build an evidence-backed Skill Passport",
      "Get matched to internships and jobs that fit your real skills",
    ],
  },
  {
    role: "Industry",
    icon: "🏢",
    points: [
      "Find candidates with verified, demonstrated skills",
      "See explainable match scores — not black-box rankings",
      "Post requirements at the competency level, not just keywords",
      "Reduce time-to-shortlist with pre-filtered talent",
    ],
  },
  {
    role: "Institutions",
    icon: "🏛️",
    points: [
      "See which skills your students lack relative to industry demand",
      "Track readiness, internship participation, and placement outcomes",
      "Identify curriculum gaps before they affect placements",
      "Benchmark your students against national skill demand trends",
    ],
  },
  {
    role: "Faculty",
    icon: "👨‍🏫",
    points: [
      "Mentor students with visibility into their skill gaps",
      "Verify student evidence and certifications",
      "Participate in industry collaborations, FDPs, and research",
      "Contribute assessment questions to the question bank",
    ],
  },
];

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Nav */}
      <nav className="border-b border-slate-200 sticky top-0 z-50 bg-white/80 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/" className="font-bold text-primary-700 text-xl">
            SkillMesh
          </Link>
          <div className="flex items-center gap-4">
            <Link
              href="/login"
              className="text-sm text-slate-600 hover:text-primary-600 font-medium"
            >
              Sign in
            </Link>
            <Link
              href="/register"
              className="text-sm font-semibold bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition"
            >
              Get started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 py-20 text-center">
        <p className="text-sm font-semibold text-primary-600 uppercase tracking-wide mb-4">
          How it works
        </p>
        <h1 className="text-4xl sm:text-5xl font-bold text-slate-900 leading-tight mb-6">
          From assessment to opportunity — evidence all the way
        </h1>
        <p className="text-lg text-slate-500 max-w-2xl mx-auto">
          SkillMesh doesn't just store what you claim to know. It builds an
          evidence-backed competency profile, identifies your gaps, recommends
          ways to close them, and connects you with the right opportunities.
        </p>
      </section>

      {/* Core loop */}
      <section className="bg-slate-50 border-y border-slate-200 py-8 px-6">
        <div className="max-w-5xl mx-auto flex flex-wrap items-center justify-center gap-3 text-sm font-medium text-slate-600">
          {["Measure", "Understand", "Learn", "Prove", "Match", "Outcome", "Improve"].map(
            (step, i, arr) => (
              <span key={step} className="flex items-center gap-3">
                <span className="bg-primary-600 text-white px-3 py-1.5 rounded-full text-xs font-semibold">
                  {step}
                </span>
                {i < arr.length - 1 && (
                  <span className="text-slate-300 text-lg">→</span>
                )}
              </span>
            ),
          )}
        </div>
      </section>

      {/* Steps */}
      <section className="max-w-4xl mx-auto px-6 py-20">
        <h2 className="text-2xl font-bold text-slate-900 mb-12 text-center">
          The six steps
        </h2>
        <div className="space-y-6">
          {STEPS.map((step) => (
            <div
              key={step.number}
              className={`rounded-2xl border p-6 sm:p-8 ${step.color}`}
            >
              <div className="flex items-start gap-5">
                <div className="flex-shrink-0">
                  <span className={`text-4xl font-black ${step.numColor} opacity-20 leading-none`}>
                    {step.number}
                  </span>
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">{step.icon}</span>
                    <h3 className="font-bold text-slate-900 text-lg">
                      {step.title}
                    </h3>
                  </div>
                  <p className="text-slate-600 text-sm leading-relaxed">
                    {step.description}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Who it's for */}
      <section className="bg-slate-50 border-t border-slate-200 px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl font-bold text-slate-900 mb-12 text-center">
            Built for everyone in the ecosystem
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {FOR_WHOM.map((group) => (
              <div
                key={group.role}
                className="bg-white rounded-2xl border border-slate-200 p-6"
              >
                <div className="flex items-center gap-3 mb-4">
                  <span className="text-2xl">{group.icon}</span>
                  <h3 className="font-bold text-slate-900">{group.role}</h3>
                </div>
                <ul className="space-y-2">
                  {group.points.map((point) => (
                    <li key={point} className="flex items-start gap-2 text-sm text-slate-600">
                      <span className="text-primary-500 mt-0.5 flex-shrink-0">✓</span>
                      {point}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* What makes it different */}
      <section className="max-w-4xl mx-auto px-6 py-20">
        <h2 className="text-2xl font-bold text-slate-900 mb-4 text-center">
          What makes SkillMesh different
        </h2>
        <p className="text-slate-500 text-center mb-12 text-sm">
          Most platforms store what you claim. We measure what you can prove.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {[
            {
              icon: "🔍",
              title: "Evidence-backed",
              desc: "Every skill is classified as Claimed, Demonstrated, or Verified. Self-declarations don't carry the same weight as assessment results.",
            },
            {
              icon: "📐",
              title: "Explainable scoring",
              desc: "All proficiency scores, readiness scores, and match scores use documented, deterministic algorithms — not AI black boxes.",
            },
            {
              icon: "📉",
              title: "Gap closure tracking",
              desc: "We don't just show you your gaps — we measure whether the platform helped you close them. Gap Closure % is a first-class metric.",
            },
          ].map((item) => (
            <div
              key={item.title}
              className="bg-slate-50 rounded-xl border border-slate-200 p-6 text-center"
            >
              <div className="text-3xl mb-3">{item.icon}</div>
              <h3 className="font-semibold text-slate-900 mb-2">{item.title}</h3>
              <p className="text-sm text-slate-500 leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="bg-primary-600 px-6 py-16 text-center">
        <h2 className="text-3xl font-bold text-white mb-4">
          Ready to prove your skills?
        </h2>
        <p className="text-primary-200 mb-8 text-sm">
          Join students, faculty, and industry partners on SkillMesh.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/register"
            className="inline-block bg-white text-primary-700 font-semibold px-8 py-3 rounded-lg hover:bg-primary-50 transition text-sm"
          >
            Create account
          </Link>
          <Link
            href="/login"
            className="inline-block border border-primary-400 text-white font-semibold px-8 py-3 rounded-lg hover:bg-primary-700 transition text-sm"
          >
            Sign in
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 px-6 py-8">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-sm text-slate-400">
            SkillMesh — SIH 2026 · Problem Statement SIH26044
          </p>
          <p className="text-sm text-slate-400">
            Ministry of Ayush · All India Institute of Ayurveda
          </p>
        </div>
      </footer>
    </div>
  );
}
