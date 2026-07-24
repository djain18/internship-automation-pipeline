import Board from "../components/Board";

export default function Internships({ listings = [], loading, onOpen }) {
  return <Board listings={listings} loading={loading} onOpen={onOpen} />;
}
