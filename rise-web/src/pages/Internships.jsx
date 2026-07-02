import Board from "../components/Board";

export default function Internships({ listings = [], loading, onOpen }) {
  return (
    <div className="pt-6">
      <Board listings={listings} loading={loading} onOpen={onOpen} />
    </div>
  );
}
