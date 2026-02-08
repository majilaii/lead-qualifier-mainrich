import Navbar from "./components/Navbar";
import InfiniteRolodex from "./components/InfiniteRolodex";
import StatsBar from "./components/StatsBar";
import HowItWorks from "./components/HowItWorks";
import Pipeline from "./components/Pipeline";
import Features from "./components/Features";
import CTA from "./components/CTA";
import Footer from "./components/Footer";

export default function Home() {
  return (
    <>
      <Navbar />
      <main>
        <InfiniteRolodex />
        <StatsBar />
        <HowItWorks />
        <Pipeline />
        <Features />
        <CTA />
      </main>
      <Footer />
    </>
  );
}
