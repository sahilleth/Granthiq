"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Sparkles,
  FileText,
  Brain,
  Zap,
  BookOpen,
  ChevronDown,
  CheckCircle2,
  MessageSquareQuote,
} from "lucide-react";
import { motion, useScroll, useTransform } from "framer-motion";
import {
  fadeUp,
  fadeUpSpring,
  scaleIn,
  popIn,
  staggerContainer,
  staggerContainerSlow,
  cardItem,
  defaultViewport,
} from "@/lib/motion";
import { AvatarCircles } from "@/components/magicui/avatar-circles";
import { TypingAnimation } from "@/components/magicui/typing-animation";
import { FlipWords } from "@/components/ui/flip-words";
import ShimmerButton from "@/components/magicui/shimmer-button";
import { BRAND, HERO_PHRASES } from "@/lib/brand";

const floatingIcons = [
  { Icon: FileText, delay: 0, position: "top-[15%] left-[8%]", rotate: "-6deg" },
  { Icon: Brain, delay: 0.5, position: "top-[25%] right-[12%]", rotate: "6deg" },
  { Icon: Zap, delay: 1, position: "bottom-[30%] left-[5%]", rotate: "-3deg" },
  { Icon: BookOpen, delay: 1.5, position: "bottom-[20%] right-[8%]", rotate: "3deg" },
];

const avatars = [
  {
    imageUrl: "https://avatars.githubusercontent.com/u/16860528",
    profileUrl: "https://github.com/dillionverma",
  },
  {
    imageUrl: "https://avatars.githubusercontent.com/u/20110627",
    profileUrl: "https://github.com/tomonarifeehan",
  },
  {
    imageUrl: "https://avatars.githubusercontent.com/u/106103625",
    profileUrl: "https://github.com/BankkRoll",
  },
  {
    imageUrl: "https://avatars.githubusercontent.com/u/59228569",
    profileUrl: "https://github.com/safethecode",
  },
  {
    imageUrl: "https://avatars.githubusercontent.com/u/59442788",
    profileUrl: "https://github.com/sanjay-mali",
  },
  {
    imageUrl: "https://avatars.githubusercontent.com/u/89768406",
    profileUrl: "https://github.com/itsarghyadas",
  },
];

// Rotating focus areas in the subheadline
const researchPhrases = [...HERO_PHRASES];

export function LandingHero() {
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  // Parallax for hero visual
  const { scrollYProgress } = useScroll();
  const heroY = useTransform(scrollYProgress, [0, 0.3], [0, -40]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePos({ x: e.clientX, y: e.clientY });
    };
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  return (
    <section className="relative min-h-[95vh] flex items-center justify-center overflow-hidden pt-20 lg:pt-24">
      {/* Animated Background Gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-surface-0 via-surface-0 to-surface-1" />

      {/* Radial gradient accent - enhanced */}
      <div
        className="absolute inset-0 opacity-50 animate-gradient-shift"
        style={{
          background: `
            radial-gradient(ellipse 80% 50% at 50% -20%, oklch(0.78 0.22 132 / 0.18), transparent),
            radial-gradient(ellipse 60% 40% at 100% 50%, oklch(0.52 0.11 132 / 0.10), transparent),
            radial-gradient(ellipse 60% 40% at 0% 50%, oklch(0.78 0.22 132 / 0.10), transparent)
          `,
          backgroundSize: "200% 200%",
        }}
      />

      {/* Cursor-reactive glow */}
      <div
        className="fixed pointer-events-none z-10 w-[600px] h-[600px] rounded-full opacity-25 hidden lg:block"
        style={{
          background: "radial-gradient(circle, oklch(0.78 0.22 132 / 0.25) 0%, transparent 70%)",
          left: mousePos.x - 300,
          top: mousePos.y - 300,
          transition: "left 0.2s ease-out, top 0.2s ease-out",
        }}
      />

      {/* Grid pattern overlay */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `
            linear-gradient(var(--border) 1px, transparent 1px),
            linear-gradient(90deg, var(--border) 1px, transparent 1px)
          `,
          backgroundSize: "64px 64px",
        }}
      />

      {/* Floating icons with framer-motion animations */}
      {floatingIcons.map(({ Icon, delay, position, rotate }, index) => (
        <motion.div
          key={index}
          className={`absolute ${position} hidden lg:flex items-center justify-center w-14 h-14 rounded-2xl bg-surface-1 border border-border shadow-lg hover-lift`}
          style={{
            rotate,
          }}
          initial={{ opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1, y: [0, -8, 0] }}
          transition={{
            opacity: { duration: 0.5, delay: delay + 0.3 },
            scale: { duration: 0.5, delay: delay + 0.3, type: "spring", stiffness: 300, damping: 20 },
            y: { repeat: Infinity, duration: 2.5, ease: "easeInOut", delay: delay + 0.8 },
          }}
        >
          <Icon className="w-6 h-6 text-synapse-500" />
        </motion.div>
      ))}

      {/* Content */}
      <motion.div
        className="relative z-20 max-w-5xl mx-auto px-6 lg:px-8 text-center"
        variants={staggerContainerSlow}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-40px" }}
      >
        {/* Badge - bouncy entrance */}
        <motion.div
          variants={popIn}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-surface-2 border border-border text-sm text-muted-foreground mb-8"
        >
          <Sparkles className="w-4 h-4 text-synapse-500 animate-pulse-scale" />
          <span>{BRAND.tagline}</span>
          <span className="px-2 py-0.5 rounded-full bg-synapse-500/10 text-synapse-600 text-xs font-medium">
            Open source
          </span>
        </motion.div>

        {/* Headline */}
        <motion.h1
          variants={fadeUpSpring}
          className="text-4xl sm:text-5xl lg:text-6xl xl:text-7xl font-bold leading-[1.1] tracking-tight text-foreground mb-6"
        >
          Read like a scholar.{" "}
          <br className="hidden sm:block" />
          <span className="relative inline-block">
            <TypingAnimation 
              text="Answer with proof." 
              className="relative z-10 text-synapse-500 text-4xl sm:text-5xl lg:text-6xl xl:text-7xl font-bold leading-[1.1] tracking-tight" 
              duration={100}
            />
            <span
              className="absolute -bottom-2 left-0 right-0 h-3 bg-synapse-500/20 rounded-full -z-0"
              style={{ transform: "skewX(-6deg)" }}
            />
          </span>
        </motion.h1>

        {/* Subheadline - Agitate the problem, then solve */}
        <motion.div
          variants={fadeUp}
          className="text-lg lg:text-xl text-muted-foreground max-w-2xl mx-auto mb-6 leading-relaxed"
        >
          <p className="mb-2">
            Most tools summarize. <span className="text-foreground font-semibold">{BRAND.name}</span> retrieves, cites, and shows its work.
          </p>
          <p>
            Built for people wrestling with real sources — so you can ship{" "}
            <span className="inline-block align-bottom px-1">
              <FlipWords 
                words={researchPhrases} 
                className="text-synapse-500 font-medium !px-0 leading-none"
                duration={3000}
              />
            </span>{" "}
            faster, without losing the thread.
          </p>
        </motion.div>

        {/* Quick benefits - visual checklist */}
        <motion.div
          variants={fadeUp}
          className="flex flex-wrap justify-center gap-4 mb-8"
        >
          {[
            "Ingest any source",
            "Ask in plain language",
            "Every claim cited",
          ].map((benefit) => (
            <div
              key={benefit}
              className="flex items-center gap-1.5 text-sm text-muted-foreground"
            >
              <CheckCircle2 className="w-4 h-4 text-synapse-500" />
              <span>{benefit}</span>
            </div>
          ))}
        </motion.div>

        {/* CTA Buttons - benefit-focused */}
        <motion.div
          variants={fadeUpSpring}
          className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-10"
        >
          <motion.div
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
          >
            <Link href="/auth/sign-up">
              <ShimmerButton
                className="h-14 px-10 text-base font-semibold shadow-lg shadow-synapse-500/25 hover:shadow-xl hover:shadow-synapse-500/35 transition-all duration-300 gap-2"
                background="oklch(0.78 0.22 132)"
                shimmerColor="#050505"
                shimmerDuration="2s"
              >
                Open a free notebook
                <ArrowRight className="w-4 h-4 ml-2" />
              </ShimmerButton>
            </Link>
          </motion.div>
        </motion.div>

        {/* Trust signals - enhanced with real context */}
        <motion.div
          variants={fadeUp}
          className="flex flex-wrap items-center justify-center gap-6 text-sm text-muted-foreground"
        >
          <div className="flex items-center gap-2">
            <AvatarCircles numPeople={99} avatarUrls={avatars} />
            <span><span className="font-semibold text-foreground">Self-hostable</span> · your data stays yours</span>
          </div>
          <span className="hidden sm:inline text-border">•</span>
          <span>Hybrid search + <span className="font-medium text-foreground">research agent</span></span>
          <span className="hidden sm:inline text-border">•</span>
          <span className="text-synapse-500 font-medium flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5" />
            {BRAND.etymology.split("—")[0].trim()}
          </span>
        </motion.div>

        {/* Hero Visual - Enhanced mockup with parallax */}
        <motion.div
          variants={scaleIn}
          style={{ y: heroY }}
          className="relative mt-16 lg:mt-20"
        >
          <div className="relative mx-auto max-w-4xl">
            {/* Glow behind - enhanced */}
            <div className="absolute -inset-8 bg-gradient-to-r from-synapse-500/25 via-transparent to-cognition-500/25 rounded-3xl blur-3xl opacity-60 animate-gradient-shift" />

            {/* App preview mockup */}
            <div className="relative rounded-2xl overflow-hidden border border-border bg-surface-1 shadow-2xl hover-lift-lg">
              {/* Browser chrome */}
              <div className="flex items-center gap-2 px-4 py-3 bg-surface-2 border-b border-border">
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-red-500/60 hover:bg-red-500 transition-colors" />
                  <div className="w-3 h-3 rounded-full bg-yellow-500/60 hover:bg-yellow-500 transition-colors" />
                  <div className="w-3 h-3 rounded-full bg-green-500/60 hover:bg-green-500 transition-colors" />
                </div>
                <div className="flex-1 flex justify-center">
                  <div className="px-4 py-1 rounded-md bg-surface-3 text-xs text-muted-foreground">
                    app.{BRAND.appUrl}
                  </div>
                </div>
              </div>

              {/* App content mockup */}
              <div className="aspect-[16/9] bg-surface-0 p-4 sm:p-6 lg:p-8 min-h-[280px]">
                <div className="grid grid-cols-12 gap-3 sm:gap-4 h-full min-h-[220px]">
                  {/* Sources sidebar */}
                  <div className="col-span-3 flex flex-col rounded-xl border border-border-emphasis bg-surface-1/80 p-3 sm:p-4 overflow-hidden">
                    <p className="text-[10px] sm:text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                      Sources
                    </p>
                    <div className="space-y-2 flex-1">
                      {[
                        { name: "thesis-ch3.pdf", active: true },
                        { name: "field-notes.md", active: false },
                        { name: "lecture-04.mp3", active: false },
                      ].map((source) => (
                        <div
                          key={source.name}
                          className={`flex items-center gap-2 rounded-lg px-2 py-2 text-[10px] sm:text-xs truncate ${
                            source.active
                              ? "bg-synapse-500/15 border border-synapse-500/40 text-foreground"
                              : "bg-surface-2/80 border border-border text-muted-foreground"
                          }`}
                        >
                          <FileText className={`w-3 h-3 shrink-0 ${source.active ? "text-synapse-500" : ""}`} />
                          <span className="truncate">{source.name}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Chat panel */}
                  <div className="col-span-6 flex flex-col rounded-xl border border-border-emphasis bg-surface-1/80 p-3 sm:p-4 overflow-hidden">
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-xs sm:text-sm font-semibold text-foreground truncate">
                        Literature Survey
                      </p>
                      <span className="hidden sm:inline-flex items-center gap-1 rounded-full bg-synapse-500/15 border border-synapse-500/30 px-2 py-0.5 text-[10px] font-medium text-synapse-500">
                        Research mode
                      </span>
                    </div>

                    <div className="space-y-3 flex-1">
                      <div className="rounded-lg bg-surface-2/90 border border-border px-3 py-2">
                        <p className="text-[10px] sm:text-xs text-muted-foreground mb-0.5">You</p>
                        <p className="text-[11px] sm:text-sm text-foreground leading-snug">
                          What themes emerge in chapter 3?
                        </p>
                      </div>

                      <div className="rounded-lg bg-synapse-500/10 border border-synapse-500/25 px-3 py-2.5">
                        <div className="flex items-center gap-2 mb-1.5">
                          <MessageSquareQuote className="w-3.5 h-3.5 text-synapse-500" />
                          <p className="text-[10px] sm:text-xs font-medium text-synapse-500">{BRAND.name}</p>
                          <span className="ml-auto rounded-full bg-synapse-500/20 px-1.5 py-0.5 text-[9px] font-semibold text-synapse-500">
                            High
                          </span>
                        </div>
                        <p className="text-[11px] sm:text-sm text-foreground/90 leading-snug">
                          Three themes stand out: institutional memory, oral testimony, and archival gaps{" "}
                          <span className="inline-flex items-center rounded bg-synapse-500/25 px-1 text-[10px] font-bold text-synapse-500">
                            [1]
                          </span>
                          .
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Citations panel */}
                  <div className="col-span-3 flex flex-col rounded-xl border border-border-emphasis bg-surface-1/80 p-3 sm:p-4 overflow-hidden">
                    <p className="text-[10px] sm:text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                      Citations
                    </p>
                    <div className="space-y-2 flex-1">
                      {[
                        { page: "p. 12", score: "0.94", file: "thesis-ch3.pdf" },
                        { page: "p. 47", score: "0.88", file: "thesis-ch3.pdf" },
                      ].map((cite, i) => (
                        <div
                          key={i}
                          className="rounded-lg border border-border bg-surface-2/90 p-2"
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] font-bold text-synapse-500">[{i + 1}]</span>
                            <span className="text-[9px] text-muted-foreground">{cite.page}</span>
                          </div>
                          <p className="text-[10px] text-foreground/80 truncate">{cite.file}</p>
                          <div className="mt-1.5 h-1 rounded-full bg-surface-3 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-synapse-500"
                              style={{ width: `${parseFloat(cite.score) * 100}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Scroll indicator */}
        <motion.div
          variants={fadeUp}
          className="mt-12 flex justify-center animate-scroll-hint"
        >
          <ChevronDown className="w-6 h-6 text-muted-foreground" />
        </motion.div>
      </motion.div>
    </section>
  );
}
