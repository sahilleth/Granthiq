"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Sparkles } from "lucide-react";
import { fadeUp, fadeUpSpring } from "@/lib/motion";
import ShimmerButton from "@/components/magicui/shimmer-button";

export function LandingCTA() {
  return (
    <section
      id="final-cta"
      className="relative py-24 lg:py-32 bg-surface-0 overflow-hidden"
    >
      <div
        className="absolute inset-0 animate-gradient-shift"
        style={{
          background: `
            radial-gradient(ellipse 80% 50% at 50% 50%, oklch(0.72 0.19 132 / 0.12), transparent)
          `,
          backgroundSize: "200% 200%",
        }}
      />

      <div className="relative max-w-4xl mx-auto px-6 lg:px-8 text-center">
        <motion.h2
          variants={fadeUpSpring}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="text-3xl lg:text-4xl xl:text-5xl font-bold text-foreground mb-4"
        >
          Your next insight is{" "}
          <span className="text-synapse-500">one notebook away</span>
        </motion.h2>

        <motion.p
          variants={fadeUp}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="text-lg text-muted-foreground max-w-2xl mx-auto mb-10"
        >
          Open a notebook, add your sources, and ask questions the way you would
          in a reading room — with receipts.
        </motion.p>

        <motion.div
          variants={fadeUpSpring}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-60px" }}
          className="flex justify-center"
        >
          <Link href="/auth/sign-up">
            <ShimmerButton
              className="h-16 px-12 text-lg font-semibold shadow-xl shadow-synapse-500/30 hover:shadow-2xl hover:shadow-synapse-500/40 transition-all duration-300 gap-3 spring-transition hover:scale-105"
              background="oklch(0.65 0.17 68)"
              shimmerColor="#ffffff"
              shimmerDuration="2s"
            >
              <Sparkles className="w-5 h-5 mr-2" />
              Open a free notebook
              <ArrowRight className="w-5 h-5 ml-2" />
            </ShimmerButton>
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
