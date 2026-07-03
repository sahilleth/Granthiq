"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Logo } from "@/components/logo";
import { Github, Mail } from "lucide-react";
import { fadeUp, popIn, staggerContainerFast } from "@/lib/motion";
import { BRAND } from "@/lib/brand";

const footerLinks = [
  { label: "Features", href: "#features" },
  { label: "Documentation", href: "/docs" },
  { label: "Privacy Policy", href: "/privacy" },
  { label: "Terms of Service", href: "/tos" },
];

const socialLinks = [
  { icon: Github, href: BRAND.githubUrl, label: "GitHub" },
  { icon: Mail, href: `mailto:${BRAND.email}`, label: "Email" },
];

export function LandingFooter() {
  return (
    <footer className="bg-surface-1 border-t border-border">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-12 lg:py-16">
        <motion.div
          variants={fadeUp}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-40px" }}
          className="flex flex-col md:flex-row md:items-start md:justify-between gap-10"
        >
          <div className="max-w-sm">
            <Link href="/" className="flex items-center gap-2.5 mb-4 group">
              <Logo
                className="w-10 h-10 spring-transition group-hover:scale-110"
                showWordmark
                wordmarkClassName="text-lg font-semibold"
              />
            </Link>
            <p className="text-muted-foreground text-sm mb-6">
              {BRAND.longDescription}
            </p>
            <motion.div
              variants={staggerContainerFast}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-20px" }}
              className="flex items-center gap-3"
            >
              {socialLinks.map((social) => (
                <motion.a
                  key={social.label}
                  variants={popIn}
                  whileHover={{ y: -2, scale: 1.05 }}
                  href={social.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-10 h-10 rounded-xl bg-surface-2 border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:border-synapse-500/30 hover:bg-synapse-500/5 transition-colors"
                  aria-label={social.label}
                >
                  <social.icon className="w-4 h-4" />
                </motion.a>
              ))}
            </motion.div>
          </div>

          <ul className="flex flex-wrap gap-x-8 gap-y-3">
            {footerLinks.map((link) => (
              <li key={link.label}>
                <Link
                  href={link.href}
                  className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </motion.div>

        <motion.div
          variants={fadeUp}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-20px" }}
          className="mt-10 pt-6 border-t border-border"
        >
          <p className="text-sm text-muted-foreground">
            &copy; {new Date().getFullYear()} {BRAND.name}. Open source under MIT license.
          </p>
        </motion.div>
      </div>
    </footer>
  );
}
